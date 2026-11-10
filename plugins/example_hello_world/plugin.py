"""Minimal FDMX SDK example. Copy this folder into ~/.fdmx/plugins/."""
def register(api):
    api.log("Hello World plugin registered.")
    api.on("app.started", lambda event: api.log("FDMX started; plugin hook received event."))
    api.on("download.completed", lambda event: api.notify(
        "Download completed",
        event.get("name", "A download") + " finished."
    ))

def shutdown():
    pass
