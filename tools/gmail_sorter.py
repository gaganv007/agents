#!/usr/bin/env python3
"""Gmail AI Assistant - triage new mail and draft replies with Claude.

What it does on each run (every 30 min via the scheduler):
  - looks only at NEW unread inbox mail (your existing backlog is ignored)
  - asks Claude to classify each email and decide if it expects a reply
  - moves it: spam/ads -> Spam, orders -> Orders, receipts/newsletters/etc ->
    their own labels (all configurable in config.json)
  - if a real person / recruiter is expecting a reply, creates a review-ready
    DRAFT (never sent) written by Claude

Modes:
  triage  : the above (default; what the scheduler runs)
  search  : run any Gmail query and list matches
  reset   : mark "now" as the starting point (ignore everything before it)

Setup: needs credentials.json (see README) and your Anthropic key in .env:
  echo 'ANTHROPIC_API_KEY=sk-ant-...' > ~/Desktop/agents/.env
"""
import os
import sys
import json
import time
import base64
import argparse
import urllib.request
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config, ROOT, get_secret  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CRED_PATH = os.path.join(ROOT, "credentials.json")
TOKEN_PATH = os.path.join(ROOT, "token.json")
OWNER = "Gagan"
CATEGORIES = ["spam", "advertising", "order", "receipt", "newsletter",
              "social", "notification", "job", "personal", "other"]


# ---------------------------------------------------------------- auth / libs
def _have_libs():
    try:
        import googleapiclient.discovery  # noqa
        import google_auth_oauthlib.flow  # noqa
        import google.oauth2.credentials  # noqa
        return True
    except ImportError:
        return False


def get_service():
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CRED_PATH):
                raise FileNotFoundError("credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(CRED_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _preflight(need_key=True):
    if not _have_libs():
        print(f"{C.RED}Google libraries not installed.{C.R}")
        print("  pip install google-api-python-client google-auth-httplib2 "
              "google-auth-oauthlib")
        return None
    if not os.path.exists(CRED_PATH):
        print(f"{C.RED}Missing credentials.json{C.R} (expected at {CRED_PATH})")
        print(f"{C.GRY}See README 'Gmail setup'.{C.R}")
        return None
    if need_key and not get_secret("ANTHROPIC_API_KEY"):
        print(f"{C.RED}No ANTHROPIC_API_KEY.{C.R} Triage uses Claude to classify "
              f"& draft.")
        print(f"{C.GRY}Add it:  echo 'ANTHROPIC_API_KEY=sk-ant-...' > "
              f"{os.path.join(ROOT, '.env')}{C.R}")
        return None
    try:
        return get_service()
    except Exception as e:
        print(f"{C.RED}Auth failed: {e}{C.R}")
        return None


# ---------------------------------------------------------------- helpers
def body_text(payload):
    def walk(p):
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", "replace")
        for part in p.get("parts", []) or []:
            t = walk(part)
            if t:
                return t
        return ""
    return walk(payload)


def _state_path(cfg):
    return os.path.join(ROOT, cfg.get("triage", {}).get("state_file", "gmail_state.json"))


def load_state(cfg):
    p = _state_path(cfg)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return {"since_ms": None, "processed": []}


def save_state(cfg, state):
    json.dump(state, open(_state_path(cfg), "w"), indent=2)


# ---------------------------------------------------------------- Claude
def classify(sender, subject, body, sig, model):
    key = get_secret("ANTHROPIC_API_KEY")
    prompt = f"""You are {OWNER}'s personal email assistant. Read the email and \
reply with ONLY a JSON object (no markdown fences, no commentary).

Shape:
{{"category": one of {CATEGORIES},
 "needs_reply": true or false,
 "draft": a reply written as {OWNER}, or null}}

Guidance:
- category: single best fit. advertising = marketing/promotions/sales. spam = \
junk/phishing. order = purchase/shipping/delivery. receipt = payment/invoice. \
job = recruiter/hiring/interview/application. personal = a real human writing \
to {OWNER}. notification = automated app/service alert. social = social network.
- needs_reply: TRUE only if a human genuinely expects a personal reply from \
{OWNER} (recruiter/hiring email, or a person asking something). FALSE for \
newsletters, ads, promotions, receipts, orders, and automated/no-reply mail.
- draft: if needs_reply is true, write a concise, warm, professional reply as \
{OWNER}, ending EXACTLY with this signature:
{sig}
Otherwise draft must be null.

Email:
From: {sender}
Subject: {subject}

{body[:4000]}"""
    payload = {"model": model, "max_tokens": 800,
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
    # tolerate stray prose around the JSON
    s, e = text.find("{"), text.rfind("}")
    obj = json.loads(text[s:e + 1]) if s >= 0 else {}
    cat = obj.get("category", "other")
    if cat not in CATEGORIES:
        cat = "other"
    return cat, bool(obj.get("needs_reply")), obj.get("draft")


# ---------------------------------------------------------------- TRIAGE
def _ensure_label(service, name, cache):
    if name not in cache:
        lb = service.users().labels().create(userId="me", body={"name": name}).execute()
        cache[name] = lb["id"]
    return cache[name]


def triage(apply=False, assume_yes=False, since_hours=None):
    header("Gmail - AI triage", "[MAIL]")
    service = _preflight(need_key=True)
    if not service:
        return {}
    cfg = load_config()["gmail_sorter"]
    tcfg = cfg.get("triage", {})
    catmap = tcfg.get("categories", {})
    sig = cfg.get("signature", "Best,\nGagan")
    model = cfg.get("model", "claude-sonnet-4-6")
    now_ms = int(time.time() * 1000)

    state = load_state(cfg)
    if since_hours is not None:
        window = now_ms - int(since_hours * 3600 * 1000)
        persist = False
    elif state.get("since_ms") is None:
        # first ever run: mark "now" and ignore the whole existing backlog
        state["since_ms"] = now_ms
        save_state(cfg, state)
        print(f"  {C.GRN}Starting point set to now. Existing emails are ignored; "
              f"new mail will be handled from here.{C.R}")
        return {"started": True}
    else:
        window = state["since_ms"]
        persist = True
    processed = set(state.get("processed", []))

    labels = {lb["name"]: lb["id"] for lb in
              service.users().labels().list(userId="me").execute().get("labels", [])}
    drafted_threads = set()
    for d in service.users().drafts().list(userId="me", maxResults=100).execute().get("drafts", []):
        tid = d.get("message", {}).get("threadId")
        if tid:
            drafted_threads.add(tid)

    msgs = service.users().messages().list(
        userId="me", labelIds=["INBOX", "UNREAD"],
        maxResults=cfg.get("max_messages", 50)).execute().get("messages", [])

    summary = {"processed": 0, "spam": 0, "sorted": 0, "drafts": 0, "kept": 0}
    actions = []
    for m in msgs:
        if m["id"] in processed:
            continue
        full = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        if int(full.get("internalDate", 0)) < window:
            continue  # older than our starting point -> ignore
        h = {x["name"]: x["value"] for x in full["payload"].get("headers", [])}
        sender = h.get("From", "")
        subject = h.get("Subject", "(no subject)")
        try:
            cat, needs_reply, draft = classify(sender, subject, body_text(full["payload"]), sig, model)
        except Exception as e:
            print(f"  {C.RED}classify failed for '{subject[:40]}': {e}{C.R}")
            continue

        rule = catmap.get(cat, {"action": "none"})
        act = rule.get("action", "none")
        add, remove, dest = [], [], "inbox"
        if act == "spam":
            add, remove, dest = ["SPAM"], ["INBOX"], "Spam"
        elif act == "label":
            add = [_ensure_label(service, rule["label"], labels)]
            dest = rule["label"]
            if rule.get("archive"):
                remove = ["INBOX"]

        will_draft = needs_reply and draft and full["threadId"] not in drafted_threads
        actions.append((subject[:48], sender[:30], cat, dest, will_draft))

        if apply:
            try:
                if add or remove:
                    service.users().messages().modify(
                        userId="me", id=m["id"],
                        body={"addLabelIds": add, "removeLabelIds": remove}).execute()
                if will_draft:
                    mime = MIMEText(draft)
                    mime["To"] = sender
                    mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
                    msgid = h.get("Message-ID") or h.get("Message-Id", "")
                    if msgid:
                        mime["In-Reply-To"] = msgid
                        mime["References"] = msgid
                    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
                    service.users().drafts().create(
                        userId="me",
                        body={"message": {"raw": raw, "threadId": full["threadId"]}}).execute()
                    drafted_threads.add(full["threadId"])
            except Exception as e:
                print(f"  {C.RED}action failed for '{subject[:40]}': {e}{C.R}")
                continue

        processed.add(m["id"])
        summary["processed"] += 1
        if act == "spam":
            summary["spam"] += 1
        elif act == "label":
            summary["sorted"] += 1
        else:
            summary["kept"] += 1
        if will_draft:
            summary["drafts"] += 1

    # report
    if not actions:
        print(f"  {C.GRN}No new mail to handle.{C.R}")
    else:
        verb = "Did" if apply else "Would do"
        print(f"  {verb} the following for {len(actions)} new emails:\n")
        for subj, frm, cat, dest, drew in actions:
            tag = f"{C.MAG}+ draft reply{C.R}" if drew else ""
            arrow = "stays in inbox" if dest == "inbox" else f"-> {dest}"
            print(f"      {C.GRY}{cat:<12}{C.R} {arrow:<22} {subj}  {tag}")
        print(f"\n  {C.B}{summary['sorted']}{C.R} sorted, "
              f"{C.B}{summary['spam']}{C.R} to spam, "
              f"{C.B}{summary['drafts']}{C.R} drafts, "
              f"{C.B}{summary['kept']}{C.R} kept in inbox.")

    if apply and persist:
        state["since_ms"] = now_ms
        state["processed"] = list(processed)[-300:]
        save_state(cfg, state)
    if not apply:
        print(f"\n{C.YEL}Preview only - nothing changed. Run with --apply.{C.R}")
    return summary


# ---------------------------------------------------------------- SEARCH
def search(query, limit=20):
    header(f"Gmail - Search: {query!r}", "[MAIL]")
    service = _preflight(need_key=False)
    if not service:
        return
    msgs = service.users().messages().list(
        userId="me", q=query, maxResults=limit).execute().get("messages", [])
    if not msgs:
        print(f"{C.GRN}No messages matched.{C.R}")
        return
    print(f"  {C.B}{len(msgs)}{C.R} matches:\n")
    for m in msgs:
        meta = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]).execute()
        h = {x["name"]: x["value"] for x in meta["payload"].get("headers", [])}
        print(f"  {C.B}{h.get('Subject','(no subject)')[:60]}{C.R}")
        print(f"    {C.MAG}{h.get('From','')[:38]}{C.R}  {C.GRY}{h.get('Date','')[:25]}{C.R}")
        print(f"    {C.GRY}{meta.get('snippet','')[:80]}{C.R}\n")


def reset():
    cfg = load_config()["gmail_sorter"]
    state = load_state(cfg)
    state["since_ms"] = int(time.time() * 1000)
    state["processed"] = []
    save_state(cfg, state)
    print(f"{C.GRN}Starting point reset to now. Earlier emails will be ignored.{C.R}")


# ---------------------------------------------------------------- entry points
def run(apply=False, assume_yes=False):
    """Default action used by the scheduler = AI triage."""
    return triage(apply=apply, assume_yes=assume_yes)


def interactive():
    print(f"\n  {C.B}Gmail:{C.R}  {C.GRN}1{C.R} Triage new mail (AI)   "
          f"{C.GRN}2{C.R} Search   {C.GRN}3{C.R} Test on last 24h   "
          f"{C.GRN}4{C.R} Reset start point")
    try:
        choice = input(f"  {C.CYN}> {C.R}").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if choice == "1":
        triage(apply=False)
        from common import confirm
        if confirm("\nApply these actions (sort + create drafts)?"):
            triage(apply=True, assume_yes=True)
    elif choice == "2":
        try:
            q = input(f"  {C.CYN}Gmail search query: {C.R}").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if q:
            search(q)
    elif choice == "3":
        triage(apply=False, since_hours=24)
        from common import confirm
        if confirm("\nApply to these last-24h emails?"):
            triage(apply=True, assume_yes=True, since_hours=24)
    elif choice == "4":
        reset()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gmail AI triage / search.")
    p.add_argument("mode", nargs="?", default="triage",
                   choices=["triage", "search", "reset"])
    p.add_argument("query", nargs="?", help="search query (mode=search)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--hours", type=float, default=None,
                   help="triage emails from the last N hours (testing)")
    a = p.parse_args()
    if a.mode == "search":
        search(a.query or "is:unread")
    elif a.mode == "reset":
        reset()
    else:
        triage(apply=a.apply, assume_yes=a.yes, since_hours=a.hours)
