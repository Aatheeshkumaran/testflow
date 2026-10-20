# TestFlow

Training-operations portal that sits beside your LMS. The LMS runs lessons and tests; **TestFlow shows
Management whether mentors are really conducting tests, records marks and test dates, and visualises
student and mentor performance.** It is for staff only. Students never log in.

## What each role can do

| | Admin | Management | Mentor |
|---|---|---|---|
| Admin Control Center (accounts, roles, activate/deactivate, audit log) | Yes | No | No |
| Overview, mentor test monitor, leaderboard, all charts | Yes | Yes | Own scorecard only |
| Batches, students, tests, marks: view | All | All | Only their own batches |
| Create batches / students / assign tasks | Yes | Yes | No |
| Schedule tests, complete / cancel / reschedule, enter marks | Yes | Yes | Own tests, own batches only |
| Post task progress | No | No | Own tasks |
| CSV reports | All | All | Only their own students |

Every rule is enforced in the backend (`accounts/permissions.py`, scoped querysets in `portal/analytics.py`).
Typing an admin URL as a Mentor gives a 403; opening another mentor's student gives a 404.

**Responsibility model:** a mentor is attached to one or more **batches**. Their students, tests and
notifications are everything inside those batches. A test belongs to the mentor who conducts it; a
co-mentor in the same batch can *view* it but not edit it.

## Setup (Windows, PowerShell, VS Code)

```powershell
.\setup.ps1                              # venv + install + check + makemigrations + migrate
python manage.py createsuperuser         # becomes an Admin automatically
python manage.py runserver               # http://127.0.0.1:8000/
```
Do this in a **new folder**. This project has a new database schema, so do not point it at the old project's
`db.sqlite3`. Keep your old folder as a backup.

Optional demo data (DEBUG only) so every chart has something to show:
`python manage.py seed_demo --confirm` then sign in as `demo_admin`, `demo_manager`, `demo_mentor1..3`
(password `Demo@12345`). Mentor 1 is diligent, mentor 2 is patchy, mentor 3 stopped testing. Delete `db.sqlite3` yourself if you want a clean start.

## Creating users
Sign in as Admin → **Admin Control Center → Create account**. Pick the role, set a temporary password.
The user is forced to choose their own password at first login. The temporary password is stored hashed and never shown again.
Then: create a **Batch** (Management/Admin), attach mentors to it, add students.

## How "is the mentor conducting tests?" works
1. Each batch has a **test interval** (days). Set per batch, not global.
2. A batch is *overdue* when `last completed test + interval` has passed. If it never had a test, the clock starts at the batch start date.
3. A test whose date has passed with no outcome shows as **Missed**. Mentors must mark it completed, cancelled (reason required) or rescheduled (new date + reason required).
4. After completion, marks are due within 2 days (`TF_MARKS_GRACE_DAYS`). Overdue marks raise an alert.
5. Alerts go to the mentor and to Management/Admin, **once per issue per person**, and resolve themselves when the problem is fixed.
   A mentor can record a *reason* on an overdue batch. It is shown to Management but does not silence the alert.
6. Alerts refresh when dashboards load (every 5 min). For reliability also schedule a daily run in Windows Task Scheduler:
   `python manage.py sync_alerts`

## Mentor score (transparent, normalised)
Shown beside every individual metric. A metric with no denominator shows "–" (never 0% or 100%) and is left out;
remaining weights rescale. A mentor is ranked only after `TF_MIN_TESTS_FOR_RANKING` (3) tests were due in the period.

| Metric | Formula | Weight |
|---|---|---|
| Tests conducted | completed ÷ due (date passed; cancelled and missed count against) | 30 |
| Marks entered | completed tests with marks for every active student ÷ completed | 20 |
| Schedule compliance | batches within their interval ÷ active batches | 20 |
| Tasks done | completed ÷ tasks assigned in period | 15 |
| Tasks on time | finished by deadline ÷ tasks with a deadline that are finished or overdue | 15 |

Student flags: last 3 results average below `TF_ATTENTION_THRESHOLD` (50%), a drop of 15+ points, or a subject average below the threshold.
Batch-average comparisons only appear when at least 3 students have results (`TF_MIN_BATCH_SAMPLE`).
All tunables are in `config/settings.py`.

## Status: what is done, and what is verified

**Implemented:** custom user model and roles, role redirects, forced first-login password change, Admin Control Center
with audit log, batches with per-batch intervals, students, tests (list + calendar, complete / cancel / reschedule with
history), whole-class marks grid, student charts (trend vs batch average, subjects), mentor charts, Management overview and
monitor, leaderboard, tasks with daily updates, notifications with de-duplicated alerts, CSV exports (results, tests, mentors).

**Not yet built (planned):** CSV *import* of students/results, PDF export, "upcoming test" reminders, announcements,
login rate-limiting, offline copy of Chart.js (charts load it from a CDN, so the first load needs internet).

**Verification honesty:** this code was written and statically checked (Python compile, template tag balance, URL-name and
import cross-checks) but **has not been executed**; the build environment had no Django. The test suite in `tests/` (47 tests
covering roles, direct-URL access, temp passwords, scoping, marks rules, alerts, metrics and rendering every page) is written but
unrun. First run `python manage.py check`, then `python manage.py test`, and send me any failure output; expect a few small fixes.

## Project layout
`config/` settings and urls · `accounts/` user model, auth, Control Center · `portal/` models, `analytics.py` (all metrics),
`services.py` (status changes, alerts), `views/` (one module per area) · `templates/` · `static/` · `tests/`.
