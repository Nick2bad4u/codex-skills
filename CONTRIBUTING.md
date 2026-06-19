# Contributing

Keep this repository focused on reusable Codex skills under `skills/<skill-name>`.

Before submitting changes:

```powershell
npm run release:verify
npm run lint:external
```

Do not add npm publishing, release, or automation behavior that bypasses validation. Promote a skill to a standalone repository only when it has a stable trigger, workflow, and validation story.
