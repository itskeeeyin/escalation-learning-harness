"""Jira Cloud issues created from lesson follow-ups.

Outbound only. Create-issue bodies follow REST API v3: fields.project.key,
fields.summary, fields.issuetype.name, and a description document
(type doc, version 1). The response shape on a real create is id, key, and self.
This adapter returns that shape only from an explicit live send.

Docs:
- https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post
"""

import os

from integrations.base import WriteProposal
from integrations.transport import guarded_execute, require_env


class JiraAdapter:
    name = "jira"
    direction = "outbound"

    def propose_action_item(self, lesson, action, *, project_key=None):
        project_key = project_key or os.environ.get("JIRA_PROJECT", "LEARN")
        summary = f"{lesson.case_id} {action.id}: {action.title}"
        paragraph = (
            f"{action.criterion} Owner: {action.owner}. Team: {action.team}. "
            f"Cause: {lesson.cause}"
        )
        return WriteProposal(
            tool=self.name,
            operation="POST /rest/api/3/issue",
            summary=f"Create a {project_key} action item for {action.id}.",
            request={
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": "Task"},
                    "labels": ["escalation-learning", action.id.lower()],
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": paragraph}],
                        }],
                    },
                }
            },
        )

    def propose_all(self, lesson, *, project_key=None):
        return [self.propose_action_item(lesson, action, project_key=project_key) for action in lesson.actions]

    def execute(self, proposal, *, dry_run=True):
        def send():
            env = require_env(["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"])
            import base64
            from integrations.transport import http_json

            token = base64.b64encode(
                f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()
            ).decode()
            base = env["JIRA_BASE_URL"].rstrip("/")
            return http_json(
                f"{base}/rest/api/3/issue",
                method="POST",
                headers={"Authorization": f"Basic {token}"},
                body=proposal.request,
            )

        return guarded_execute(proposal, dry_run=dry_run, send=send)
