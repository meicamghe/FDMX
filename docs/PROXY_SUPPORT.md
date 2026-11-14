# Proxy support in GNS Downloader v6.46

FDMX v6.46 supports the following proxy URI schemes:

- `http://host:port` and `https://host:port`
- `socks4://host:port` and `socks4a://host:port`
- `socks5://host:port` and `socks5h://host:port`

Credentials may be embedded in the URI, for example:

```text
socks5h://username:password@127.0.0.1:1080
http://username:password@proxy.example:8080
```

Enable the proxy checkbox and enter the URI in the proxy address field. HTTP(S) proxies are applied to urllib-based downloads. SOCKS proxies are applied per download worker, including parallel byte-range requests, and are also passed to yt-dlp for YouTube tasks. Per-thread SOCKS routing prevents two simultaneous tasks from overwriting each other's proxy selection.

DNS behavior follows the scheme: `socks4` and `socks5` resolve names locally; `socks4a` and `socks5h` request remote DNS resolution through the proxy.

## Telegram MTProto proxies

Telegram MTProto links (`tg://proxy?...&secret=...` or `https://t.me/proxy?...&secret=...`) are not HTTP or SOCKS proxies and cannot be entered directly as a proxy URI. To use an MTProto endpoint with FDMX, run a trusted local MTProto-to-SOCKS gateway, configure it to listen on localhost (for example port 1080), then set FDMX to `socks5h://127.0.0.1:1080`. The gateway must be running for the duration of the download. FDMX does not currently parse Telegram MTProto links or launch/manage a gateway itself.

## Runtime dependency

SOCKS support uses PySocks. It is included in the Windows/Linux packaging workflow and bundled into the application build. Source installations should install it with:

```bash
python -m pip install PySocks
```

No live proxy or YouTube network test is part of the offline regression suite; test connectivity in the target network before relying on a proxy endpoint.
