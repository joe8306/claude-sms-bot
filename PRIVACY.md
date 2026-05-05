# Privacy Policy

**Last updated:** 2026-05-05

## Scope

This service is a personal SMS assistant operated by Chaim Citron for the
sole purpose of communicating with the operator's own personal phone number.
It is not a public service, has no external users, and is not used to
contact anyone other than the operator.

## What is collected

When the operator sends an SMS to the registered Twilio phone number, the
following data is processed:

- The sender's phone number (the operator's own number)
- The text content of the SMS
- A timestamp

This data is transmitted via Twilio (twilio.com) to a server hosted on
Render (render.com), where it is forwarded to Anthropic's Claude API
(anthropic.com) to generate a response. The response is returned to the
operator via SMS.

A short rolling history of recent messages may be temporarily stored on the
server to provide conversational context. This history is automatically
truncated to the last 20 user/assistant exchanges and is wiped on server
restart.

## Third parties

- **Twilio** processes inbound and outbound SMS traffic. See
  https://www.twilio.com/legal/privacy
- **Anthropic** processes message content to generate AI responses. See
  https://www.anthropic.com/legal/privacy
- **Render** hosts the application server. See
  https://render.com/privacy

## Data sharing

No data is shared with any party other than the third-party processors
listed above, all of which are required to handle the data only for
purposes of providing their service.

## Retention

Conversation history is held in volatile storage and is not backed up.
Messages persist only until the server is restarted, at which point the
history is cleared. There are no long-term records.

## Opt-out

The operator can wipe all stored conversation history at any time by
restarting the application or hitting the `/reset` endpoint.

## Contact

For questions: chaimcitron@gmail.com
