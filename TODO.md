# Dashboard, Settings, Profile Cleanup — Complete

## Completed
- [x] 1. **Departments**: Already seeded in `setup_oracle.py` (HR, IT, Finance, Production, Administration, Security). Profile page already has department dropdown, saves to Oracle, dashboard displays `summary.department`.
- [x] 2. **Appearance**: No "Appearance" section exists in settings — nothing to remove.
- [x] 3. **Notifications**: Already show "Coming Soon" badges — no functional switches present.
- [x] 4. **Security**: Password change, Face registration, Lockout policy all working. No non-functional options.
- [x] 5. **Active Sessions**: Shows JWT session info (signed in as, token expiry, issued, refresh token). Revoke All button calls `API.del('/auth/sessions')` which works.
- [x] 6. **Dashboard Chart**: Replaced fake `[3,5,2,8,6,4,1]` data with real login history from `/login-history` API, aggregated by day of week.
- [x] 7. **Dashboard Activity Table**: Now fetches real data from `/login-history?page_size=5` and displays it.
- [x] 8. **General**: No placeholder widgets, ghost buttons, or unfinished controls remain.
