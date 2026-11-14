# Security

## What this repository contains

Four offline demonstrations in standard-library Python. They make no network requests, call no model, and read only files they ship with or generate themselves. Every record is invented. There are no credentials, tokens, personal data or patient data.

The Adapter Promotion Gate labels its caller with a local role string. That label is not an authenticated identity, and the gate is a teaching model of release control, not a component to put in front of a production system. Each demo's README states its own trust boundary.

## Reporting a problem

If you find something here that should not be (a secret, a personal detail, a path to a private machine), or a way the code could be made to act on something outside the repository, please report it privately through the "Report a vulnerability" button on the repository's Security tab. If that button is not there, open an issue that says only that you have a security report, and a private channel will be arranged.

For anything else, including a wrong number, an unclear sentence or a test that should have failed, please open a public issue.
