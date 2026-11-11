# Support tool integrations

The adapters in [integrations/](../integrations/) turn public API payloads into one signal shape and turn lessons into native write requests. The default is offline. Fixtures set `sample: true` and describe themselves as fictional. CI does not set `ELH_INTEGRATIONS_MODE`. This repository does not ship credentials and is not deployed against a ServiceNow instance, a Pylon workspace, a Salesforce org, a PagerDuty account, a Slack workspace, or a Jira site.

## Direction

| Adapter | Reads | Proposed writes |
| --- | --- | --- |
| PagerDuty | Incident webhooks (v3 `event` or v2 `messages`) and `log_entries` timelines | None. Paging stays in PagerDuty. |
| Slack | Events API `message` callbacks and `conversations.replies` threads | `chat.postMessage` into the incident thread |
| ServiceNow | Table API `incident` and `problem` records (`result` object or list) | `PATCH` incident `work_notes` |
| Salesforce | Case sObject retrieve and Case change-event bodies | None. The case stays the customer record. |
| Pylon | `GET /issues/{id}` (`data` wrapper) and string-valued webhook bodies, plus the account id on the issue | None. Pylon remains the B2B support queue. |
| Jira | `jira:issue_created` and `jira:issue_updated` if a ticket is read back | `POST /rest/api/3/issue` for a lesson's action item |

`integrations/replay.py` walks one fictional path for case ESC-1042: PagerDuty page, Slack thread, ServiceNow incident and problem, Salesforce Case, Pylon issue, the existing Engineering lesson from `propose_actions`, then three proposed writes.

## Approval

`WriteGate.propose` stores the native request. `execute` raises until `approve` records a reviewer name. With `dry_run=True` (the default, and the default of `ELH_INTEGRATIONS_DRY_RUN`), approval returns the request in a receipt and does not call a transport. A live send also requires `ELH_INTEGRATIONS_MODE=live` and an explicit transport. The demo button only updates the browser tab.

## Live environment variables

Set these in the process environment when you intentionally point an adapter at a tenant you control. Do not commit them.

| Variable | Used by |
| --- | --- |
| `ELH_INTEGRATIONS_MODE=live` | Any live pull or send |
| `ELH_INTEGRATIONS_DRY_RUN=0` | Allow an approved write to call the transport |
| `SERVICENOW_INSTANCE`, `SERVICENOW_TOKEN` | Table API bearer requests |
| `PYLON_API_TOKEN` | `https://api.usepylon.com` |
| `SALESFORCE_INSTANCE_URL`, `SALESFORCE_ACCESS_TOKEN`, optional `SALESFORCE_API_VERSION` | Case retrieve |
| `PAGERDUTY_API_TOKEN` | REST API v2 `Token token=` header |
| `SLACK_BOT_TOKEN` | `conversations.replies` |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Issue retrieve and, when a write is approved and dry-run is off, issue create |

## Documentation used for field names

- ServiceNow Table API, including the problem `result` example: [Table API](https://www.servicenow.com/docs/r/xanadu/api-reference/rest-apis/c_TableAPI.html). Incident choice values New, In Progress, On Hold, Resolved, Closed, and Canceled are the incident state model: [Incident Management state model](https://www.servicenow.com/docs/bundle/xanadu-it-service-management/page/product/incident-management/concept/c_IncidentManagementStateModel.html).
- Pylon issue resource (`id`, `number`, `title`, `state`, `body_html`, `account`, `requester`, `external_incidents`): [Issues](https://docs.usepylon.com/pylon-docs/developer/api/api-reference/issues). Standard states are `new`, `waiting_on_you`, `waiting_on_customer`, `on_hold`, and `closed`. Webhook bodies are strings, including numbers: [Webhooks](https://docs.usepylon.com/pylon-docs/developer/webhooks) and [template variables](https://docs.usepylon.com/pylon-docs/platform/triggers/template-variables).
- Salesforce Case fields (`Id`, `CaseNumber`, `Subject`, `Description`, `Status`, `Priority`, `Origin`, `AccountId`, `OwnerId`, `IsClosed`, `CreatedDate`): [Case](https://developer.salesforce.com/docs/atlas.en-us.object_reference.meta/object_reference/sforce_api_objects_case.htm). Retrieve: [sObject retrieve](https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/resources_sobject_retrieve.htm). Change event header: [Change event body](https://developer.salesforce.com/docs/atlas.en-us.change_data_capture.meta/change_data_capture/cdc_event_fields_body.htm).
- PagerDuty incident `id`, `incident_number` or webhook `number`, `title`, `status` (`triggered`, `acknowledged`, `resolved`), `html_url`, `urgency`, `service`: [Get an incident](https://docs.pagerduty.com/developer/api/reference/rest/incidents/get-incident) and [v2 webhooks](https://docs.pagerduty.com/developer/webhooks-v2-overview). Timeline rows use log entry `id`, `type`, `created_at`, and `summary`: [List incident log entries](https://docs.pagerduty.com/developer/api/reference/rest/incidents/list-incident-log-entries). The v3 envelope is `event.event_type` plus `event.data`: [V3 webhooks](https://developer.pagerduty.com/docs/webhooks/v3-overview).
- Slack Events API envelope (`type`, `event_id`, `event`): [Events API](https://docs.slack.dev/apis/events-api). Threads: [conversations.replies](https://docs.slack.dev/reference/methods/conversations.replies). Outbound reply body: [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/).
- Jira create body uses `fields.project`, `fields.issuetype`, `fields.summary`, and an Atlassian document for `fields.description`: [Create issue](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-post). Webhook callbacks use `webhookEvent` and `issue`: [Webhooks](https://developer.atlassian.com/cloud/jira/platform/webhooks/).

Status values that are not in those maps stay `unknown` and keep the raw value. That is intentional: a tenant can add custom Pylon statuses or rename a Case status.
