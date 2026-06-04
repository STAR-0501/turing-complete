---
id: skill-fe-1
name: Cache Busting for Static Files
description: Flask serves static files without hashing; browser aggressively caches JS/CSS
tags: [frontend, caching, static]
---

### Skill-FE-1: Cache Busting for Static Files
- **Context**: Flask serves static files without hashing; browser aggressively caches JS/CSS.
- **What**: Add `?v=N` version query parameter to `<script>`/`<link>` tags after every meaningful JS/CSS change. Number up monotonically.
- **Why**: Without cache busting, testers/developers see stale behavior and waste time debugging phantom issues.
- **Example**: `src="/static/scripts/chat.js?v=2"`.
