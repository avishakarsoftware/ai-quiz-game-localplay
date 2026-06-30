# Archived files

## android-google-services.json
Was committed (2026-03-22, `13460ae`) at `frontend/android/app/google-services.json`, but it is **not**
a Firebase `google-services.json` — it's a GCP OAuth "installed" client-credentials file (has an
`installed` object, no `project_info`). Because Gradle auto-applies the Google Services plugin whenever a
file named `google-services.json` exists, this misplaced file failed every Android release build with
`Missing project_info object`.

Removed from the Android project on 2026-06-29 to unblock builds (LocalPlay has no Firebase plugins, and
native Google sign-in uses `@capgo/capacitor-social-login`, not `google-services.json`). Archived here for
reference only — the `client_id` is a public GCP OAuth id for project `revelryapp` (no secret).

**Do not** restore this as `google-services.json`. If Firebase push is ever added, download a *real*
`google-services.json` from the Firebase console (it will contain `project_info` + the `me.revelryapp.quiz`
package) and place it at `frontend/android/app/google-services.json`.
