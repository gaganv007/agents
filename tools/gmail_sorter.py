#!/usr/bin/env python3
"""Gmail Agent - search, sort (label/archive), and draft replies.

Modes:
  sort    : apply config rules -> labels + optional archive
  search  : run a Gmail search query and list matches
  draft   : create review-ready reply DRAFTS for emails that need a response
            (drafts are never sent; you review and send them yourself)

One-time setup: see README "Gmail setup". Needs credentials.json in this folder.

Smart drafts: if the ANTHROPIC_API_KEY environment variable is set, drafts are
written by Claude. Otherwise a polite placeholder template is used. Either way
nothing is ever sent automatically.
"""
import os
import sys
import json
import base64
import argparse
import urllib.request
from email.mime.text import MIMEText
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import C, header, load_config, ROOT, confirm  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CRED_PATH = os.path.join(ROOT, "credentials.json")
TOKEN_PATH = os.path.join(ROOT, "token.json")


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


def _preflight():
    """Returns a service or None (printing a friendly reason)."""
    if not _have_libs():
        print(f"{C.RED}Google libraries not installed.{C.R}")
        print("  pip install google-api-python-client google-auth-httplib2 "
              "google-auth-oauthlib")
        return None
    if not os.path.exists(CRED_PATH):
        print(f"{C.RED}Missing credentials.json{C.R} (expected at {CRED_PATH})")
        print(f"{C.GRY}See README 'Gmail setup' for the 5-minute steps.{C.R}")
        return None
    try:
        return get_service()
    except Exception as e:
        print(f"{C.RED}Auth failed: {e}{C.R}")
        return None


# ---------------------------------------------------------------- helpers
def headers_of(service, msg_id, names):
    meta = service.users().messages().get(
        userId="me", id=msg_id, format="metadata", metadataHeaders=names
    ).execute()
    h = {x["name"]: x["value"] for x in meta["payload"].get("headers", [])}
    return h, meta


def body_text(payload):
    """Best-effort plain-text body from a Gmail message payload."""
    def walk(p):
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(p["body"]["data"]).decode("utf-8", "replace")
        for part in p.get("parts", []) or []:
            t = walk(part)
            if t:
                return t
        return ""
    return walk(payload)


# ---------------------------------------------------------------- SORT
def _match(rule, frm, subj):
    if "from" in rule and rule["from"].lower() in frm.lower():
        return True
    if "subject" in rule and rule["subject"].lower() in subj.lower():
        return True
    return False


def sort(apply=False, assume_yes=False):
    header("Gmail - Sort inbox", "[MAIL]")
    service = _preflight()
    if not service:
        return
    cfg = load_config()["gmail_sorter"]
    rules = cfg["rules"]

    label_cache = {lb["name"]: lb["id"]
                   for lb in service.users().labels().list(userId="me")
                   .execute().get("labels", [])}

    msgs = service.users().messages().list(
        userId="me", labelIds=["INBOX"], maxResults=cfg.get("max_messages", 100)
    ).execute().get("messages", [])
    print(f"  Scanning {C.B}{len(msgs)}{C.R} inbox messages "
          f"against {len(rules)} rules...\n")

    planned = defaultdict(list)
    for m in msgs:
        h, _ = headers_of(service, m["id"], ["From", "Subject"])
        frm, subj = h.get("From", ""), h.get("Subject", "(no subject)")
        for rule in rules:
            if _match(rule, frm, subj):
                planned[(rule["label"], rule.get("archive", False))].append((m["id"], subj))
                break

    total = sum(len(v) for v in planned.values())
    if total == 0:
        print(f"{C.GRN}No inbox messages matched your rules.{C.R}")
        return
    for (label, arch), items in sorted(planned.items()):
        print(f"  {C.CYN}{label}{C.R} {C.GRY}({'label+archive' if arch else 'label'}){C.R}"
              f"  {len(items)} messages")
        for _id, subj in items[:3]:
            print(f"      {C.GRY}- {subj[:70]}{C.R}")
        if len(items) > 3:
            print(f"      {C.GRY}... and {len(items) - 3} more{C.R}")

    if not apply:
        print(f"\n{C.YEL}Preview only. Apply to label/archive {total} messages.{C.R}")
        return
    if not assume_yes and not confirm(f"\nApply changes to {total} messages?"):
        print(f"{C.GRY}Cancelled.{C.R}")
        return

    def ensure(name):
        if name not in label_cache:
            lb = service.users().labels().create(
                userId="me", body={"name": name}).execute()
            label_cache[name] = lb["id"]
        return label_cache[name]

    done = 0
    for (label, arch), items in planned.items():
        add, remove = [ensure(label)], (["INBOX"] if arch else [])
        for _id, _ in items:
            try:
                service.users().messages().modify(
                    userId="me", id=_id,
                    body={"addLabelIds": add, "removeLabelIds": remove}).execute()
                done += 1
            except Exception as e:
                print(f"{C.RED}  failed on a message: {e}{C.R}")
    print(f"\n{C.GRN}Done. Updated {done} messages.{C.R}")


# ---------------------------------------------------------------- SEARCH
def search(query, limit=20):
    header(f"Gmail - Search: {query!r}", "[MAIL]")
    service = _preflight()
    if not service:
        return
    msgs = service.users().messages().list(
        userId="me", q=query, maxResults=limit).execute().get("messages", [])
    if not msgs:
        print(f"{C.GRN}No messages matched.{C.R}")
        return
    print(f"  {C.B}{len(msgs)}{C.R} matches:\n")
    for m in msgs:
        h, meta = headers_of(service, m["id"], ["From", "Subject", "Date"])
        frm = h.get("From", "")[:38]
        subj = h.get("Subject", "(no subject)")[:60]
        snippet = meta.get("snippet", "")[:80]
        print(f"  {C.B}{subj}{C.R}")
        print(f"    {C.MAG}{frm}{C.R}  {C.GRY}{h.get('Date','')[:25]}{C.R}")
        print(f"    {C.GRY}{snippet}{C.R}\n")


# ---------------------------------------------------------------- DRAFT
def _llm_reply(sender, subject, body, dcfg):
    key = os.environ.get("ANTHROPIC_API_KEY")
    sig = dcfg.get("signature", "Best,\nGagan")
    if not key:
        return (f"Hi,\n\nThanks for your email regarding \"{subject}\". "
                f"[Draft placeholder - set ANTHROPIC_API_KEY for AI-written "
                f"replies, or edit this before sending.]\n\n{sig}")
    prompt = (
        "You are drafting a reply on behalf of Gagan. Write a concise, "
        "professional, friendly reply to the email below. Output ONLY the reply "
        "body text (no subject line, no quoted original). End with this "
        f"signature exactly:\n{sig}\n\n"
        f"From: {sender}\nSubject: {subject}\n\nEmail:\n{body[:4000]}"
    )
    payload = {
        "model": dcfg.get("model", "claude-sonnet-4-6"),
        "max_tokens": dcfg.get("max_tokens", 600),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except Exception as e:
        return (f"Hi,\n\nThanks for your email about \"{subject}\".\n\n{sig}\n"
                f"\n[AI draft failed: {e} - please write manually.]")


def draft(apply=False, assume_yes=False):
    header("Gmail - Draft replies", "[MAIL]")
    service = _preflight()
    if not service:
        return
    dcfg = load_config()["gmail_sorter"].get("draft", {})
    query = dcfg.get("query", "in:inbox is:unread -from:noreply newer_than:7d")
    max_drafts = dcfg.get("max_drafts", 10)

    # threads that already have a draft -> skip to avoid duplicates
    drafted_threads = set()
    for d in service.users().drafts().list(
            userId="me", maxResults=100).execute().get("drafts", []):
        tid = d.get("message", {}).get("threadId")
        if tid:
            drafted_threads.add(tid)

    msgs = service.users().messages().list(
        userId="me", q=query, maxResults=max_drafts * 3).execute().get("messages", [])

    candidates, seen = [], set()
    for m in msgs:
        if m["threadId"] in drafted_threads or m["threadId"] in seen:
            continue
        seen.add(m["threadId"])
        candidates.append(m)
        if len(candidates) >= max_drafts:
            break

    if not candidates:
        print(f"{C.GRN}No emails need a draft right now "
              f"(query: {query}).{C.R}")
        return

    print(f"  {C.B}{len(candidates)}{C.R} emails would get a review-ready draft:\n")
    full = []
    for m in candidates:
        meta = service.users().messages().get(
            userId="me", id=m["id"], format="full").execute()
        h = {x["name"]: x["value"] for x in meta["payload"].get("headers", [])}
        full.append((m, meta, h))
        print(f"      {C.GRY}- {h.get('Subject','(no subject)')[:60]}  "
              f"<- {h.get('From','')[:35]}{C.R}")

    if not apply:
        engine = "Claude" if os.environ.get("ANTHROPIC_API_KEY") else "template"
        print(f"\n{C.YEL}Preview only. Apply to create {len(candidates)} drafts "
              f"({engine}-written). Drafts are NEVER sent.{C.R}")
        return
    if not assume_yes and not confirm(f"\nCreate {len(candidates)} reply drafts?"):
        print(f"{C.GRY}Cancelled.{C.R}")
        return

    made = 0
    for m, meta, h in full:
        sender = h.get("From", "")
        subject = h.get("Subject", "(no subject)")
        msg_id_hdr = h.get("Message-ID") or h.get("Message-Id", "")
        reply = _llm_reply(sender, subject, body_text(meta["payload"]), dcfg)

        mime = MIMEText(reply)
        mime["To"] = sender
        mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if msg_id_hdr:
            mime["In-Reply-To"] = msg_id_hdr
            mime["References"] = msg_id_hdr
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        try:
            service.users().drafts().create(
                userId="me",
                body={"message": {"raw": raw, "threadId": m["threadId"]}}).execute()
            made += 1
        except Exception as e:
            print(f"{C.RED}  draft failed for '{subject[:30]}': {e}{C.R}")
    print(f"\n{C.GRN}Done. Created {made} drafts in your Drafts folder "
          f"(review and send when ready).{C.R}")


# ---------------------------------------------------------------- entry points
def run(apply=False, assume_yes=False):
    """Default action used by the scheduler = sort inbox."""
    sort(apply=apply, assume_yes=assume_yes)


def interactive():
    """Submenu used by the Command Center."""
    print(f"\n  {C.B}Gmail:{C.R}  {C.GRN}1{C.R} Sort inbox   "
          f"{C.GRN}2{C.R} Search   {C.GRN}3{C.R} Draft replies")
    try:
        choice = input(f"  {C.CYN}> {C.R}").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if choice == "1":
        sort(apply=False)
        if confirm("\nApply these label/archive changes now?"):
            sort(apply=True, assume_yes=True)
    elif choice == "2":
        try:
            q = input(f"  {C.CYN}Gmail search query: {C.R}").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if q:
            search(q)
    elif choice == "3":
        draft(apply=False)
        if confirm("\nCreate these drafts now?"):
            draft(apply=True, assume_yes=True)
    else:
        print(f"  {C.GRY}Nothing selected.{C.R}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gmail search / sort / draft.")
    p.add_argument("mode", nargs="?", default="sort",
                   choices=["sort", "search", "draft"])
    p.add_argument("query", nargs="?", help="search query (mode=search)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true", help="skip confirmation")
    a = p.parse_args()
    if a.mode == "search":
        search(a.query or "is:unread")
    elif a.mode == "draft":
        draft(apply=a.apply, assume_yes=a.yes)
    else:
        sort(apply=a.apply, assume_yes=a.yes)
