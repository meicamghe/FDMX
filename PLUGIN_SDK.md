# FDMX Plugin SDK 1.0

## Install
Create a folder for each plugin under:

- Windows: `%USERPROFILE%\\.fdmx\\plugins\\<plugin-id>\\`
- Linux: `~/.fdmx/plugins/<plugin-id>/`

Place `plugin.json` and the Python entrypoint in that folder. The example is in
`plugins/example_hello_world/`.

## Manifest
Required fields: `id`, `name`, `version`, `entrypoint`, `permissions`.
The entrypoint must be a Python file directly inside the plugin folder.

## Plugin contract
The entrypoint must define `register(api)`. Optional `shutdown()` is called
when the plugin is disabled. The SDK currently exposes:

- `api.log(message)` — requires `app.log`.
- `api.notify(title, message)` — requires `ui.notifications`.
- `api.on(event_name, callback)` — requires `app.events`.

Initial event names include `app.started`, `download.completed`, and
`download.failed`. Event payload fields are documented as they are added.
The download events are reserved for the next integration step; do not assume
they are emitted by every FDMX build yet.

## Enable and load
Open **Tools → Plugin Manager**, refresh the list, enable a plugin, then load it.
Disabling unloads it. A plugin hook exception unloads that plugin without
terminating the FDMX main event dispatcher.

## Security model — important
Plugins are Python code executed in the FDMX process. Permission declarations
limit access through the SDK API only; they do not restrict arbitrary Python
imports, filesystem access, network access, or subprocess creation. This release
is **not a security sandbox**. Only install plugins whose source you trust.
A separate-process worker and explicit IPC permission boundary are planned before
third-party plugins are treated as safely isolated.
