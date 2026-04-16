---
name: Upload test data to Cloudflare R2
description: Reminder to upload mouse brain and other test datasets to R2 for cloud testing and web demo
type: project
---

Upload test datasets to Cloudflare R2 for the cloud testing and web demo pipeline.

**Why:** The dev+demo network needs real data on R2 so the web demo can stream it and CI can test against it.

**How to apply:** Remind the user when they finish the current polish cycle or when they mention R2/cloud/demo setup. Datasets to upload:
- 10x_mouse_brain_2025-04-23_00-53-11.236590 (70 FOVs, 4 channels, individual TIFFs)
- Any additional test datasets the user provides
