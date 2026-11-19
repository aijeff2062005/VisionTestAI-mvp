# Hospital API (Mac MVP)

Lean FastAPI + SQLite stand-in for Frappe `smart_hospital` face/vision routes.

Runs on the **Mac** hospital host (`:8000`). The **Jetson** runs the clinic vision-test demo (AC / chart / AiFace BS), not this API.

```bash
./run.sh
# health: http://<mac-lan-ip>:8000/health
```

Routes mirror Frappe method paths used by Assistant Controller.
See [`../../docs/LAB_TOPOLOGY.md`](../../docs/LAB_TOPOLOGY.md).
