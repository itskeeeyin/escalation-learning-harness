"""Slack incident-channel threads, plus an optional status post.

Inbound messages follow conversations.replies: ok, messages[].ts, thread_ts,
user, and text. Outbound status posts follow chat.postMessage (channel, text,
thread_ts) and stay proposed until a person approves them.

Docs:
- https://api.slack.com/methods/conversations.replies
- https://api.slack.com/methods/chat.postMessage
"""

from integrations.base import EscalationSignal, WriteProposal
from integrations.fixtures import load
from integrations.transport import guarded_execute, require_env


class SlackAdapter:
    name = "slack"
    direction = "both"

    def parse_thread(self, payload):
        if payload.get("ok") is not True:
            raise ValueError("Slack conversations.replies payload is not ok.")
        messages = payload["messages"]
        if not messages:
            raise ValueError("Slack thread has no messages.")
        root = messages[0]
        text = "\n".join(message["text"] for message in messages)
        return EscalationSignal(
            tool=self.name,
            external_id=payload["channel"] + "/" + root["ts"],
            title=root["text"].split("\n", 1)[0][:120],
            status="thread",
            summary=text,
            opened_at=root["ts"],
            customer=None,
            links={"channel": payload["channel"], "thread_ts": root.get("thread_ts") or root["ts"]},
            sample=True,
        )

    def propose_status(self, lesson, *, channel, thread_ts):
        text = (
            f"Learning record {lesson.case_id}: {lesson.title}. "
            f"Cause: {lesson.cause} "
            f"Follow-ups proposed: {', '.join(action.id for action in lesson.actions)}."
        )
        return WriteProposal(
            tool=self.name,
            operation="chat.postMessage",
            summary="Post the lesson summary into the incident thread.",
            request={"channel": channel, "thread_ts": thread_ts, "text": text},
        )

    def execute(self, proposal, *, dry_run=True):
        def send():
            token = require_env(["SLACK_BOT_TOKEN"])["SLACK_BOT_TOKEN"]
            from integrations.transport import http_json

            return http_json(
                "https://slack.com/api/chat.postMessage",
                method="POST",
                headers={"Authorization": f"Bearer {token}"},
                body=proposal.request,
            )

        return guarded_execute(proposal, dry_run=dry_run, send=send)

    def load_sample(self):
        return self.parse_thread(load("slack_thread.json")).as_dict()

