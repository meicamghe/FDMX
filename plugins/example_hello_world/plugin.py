"""Minimal FDMX SDK example running in an isolated worker."""
def register(api):
    api.log("Hello World plugin registered in its worker process.")
    api.on("app.started", lambda event: api.log("FDMX started; worker received event."))
    api.on("download.completed", lambda event: api.notify(
        "Download completed", event.get("name", "A download") + " finished."
    ))
def shutdown():
    pass
