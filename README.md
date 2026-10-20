# TestFlow

**Student performance monitoring and training operations portal.**

TestFlow works alongside a Learning Management System (LMS). The LMS delivers lessons and tests; TestFlow gives
Management and Mentors one place to schedule tests, record marks and dates, and see, with charts, how students and mentors are doing.
Its main purpose is accountability: Management can see at a glance whether every mentor is actually conducting tests.

It is an internal tool for staff. Students do not log in.

---

## Features

**Mentor accountability**
- Mentor test monitor: last test conducted, tests this month, next scheduled test, missed tests and pending marks, per mentor
- Per-batch test interval, with alerts when a batch goes too long without a test
- Mentor leaderboard using normalised rates (not raw student counts), with the formula shown on the page
- Individual mentor scorecards with charts

**Students and tests**
- Batches, students and mentor assignments
- Test scheduling with list and calendar views
- Complete, cancel or reschedule a test (a reason is required for cancel and reschedule), with a full history
- Whole-class marks entry grid with live percentages and all-or-nothing validation
- Student profiles: performance trend against batch average, subject breakdown, areas of improvement, attention flags

**Operations**
- Management-assigned mentor tasks with deadlines, priorities and daily progress updates
- In-app notifications, de-duplicated and self-resolving
- CSV exports (student results, test log, mentor performance), restricted to what the user may see
- Admin Control Center: accounts, roles, activate/deactivate, audit log

**Security**
- Role-based access enforced in the backend, not just hidden in the UI
- First-login forced password change for new accounts (temporary passwords are stored hashed and never shown)
- Mentors see only the batches they are assigned to
- Profile image validation, CSRF protection, POST-only logout

## Roles

| Capability | Admin | Management | Mentor |
|---|:---:|:---:|:---:|
| Admin Control Center (accounts, roles, audit log) | ✔ | | |
| Overview, mentor monitor, leaderboard | ✔ | ✔ | Own scorecard |
| View batches, students, tests | All | All | Own batches |
| Create batches and students, assign tasks | ✔ | ✔ | |
| Schedule tests, change status, enter marks | ✔ | ✔ | Own tests |
| Post task progress | | | Own tasks |
| CSV reports | All | All | Own students |
| Edit own photo and email | ✔ | ✔ | ✔ |

A mentor is attached to one or more **batches**. Their students, tests and notifications are whatever falls inside those batches.

## Tech stack

Python · Django 5 · SQLite (PostgreSQL-ready) · HTML/CSS/JavaScript with Django templates · Chart.js · Pillow

## Getting started

Requirements: Python 3.10 or newer.

**Windows (PowerShell)**
```powershell
git clone https://github.com/Aatheeshkumaran/testflow.git
cd testflow
.\setup.ps1
python manage.py createsuperuser
python manage.py runserver
```
`setup.ps1` creates a virtual environment, installs dependencies, runs system checks, creates the migrations and applies them.
If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

**macOS / Linux**
```bash
git clone https://github.com/Aatheeshkumaran/testflow.git
cd testflow
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py makemigrations accounts portal
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/ and sign in. A superuser is always treated as an Admin.

### Demo data (development only)
```bash
python manage.py seed_demo --confirm
```
Creates sample users (`demo_admin`, `demo_manager`, `demo_mentor1` to `demo_mentor3`), batches, students, tests and marks so the charts
have something to show. It refuses to run when `TESTFLOW_DEBUG=0`. Remove the data by deleting `db.sqlite3` and migrating again.

## Using TestFlow

1. **Admin** signs in and opens **Admin Control Center → Create account** to add Management and Mentor users with temporary passwords.
2. **Admin or Management** creates a **Batch**, sets its test interval, assigns mentors, then adds students.
3. **Mentors** schedule tests for their batches, mark them completed after they take place, and enter marks.
4. **Management** watches the Overview: the mentor monitor, overdue batches, charts and leaderboard.

### How test monitoring works
- A batch is *overdue* when its last completed test plus its interval has passed. A batch that has never had a test starts counting from its start date.
- A test whose date has passed with no recorded outcome shows as **Missed** until it is completed, cancelled or rescheduled.
- Marks are due within a grace period after completion (default 2 days); late marks raise an alert.
- Alerts reach the mentor and Management once per issue, and resolve themselves when the problem is fixed. A mentor can record a reason for a delay; it is shown to Management but does not silence the alert.
- Alerts refresh when dashboards load. For reliability, schedule `python manage.py sync_alerts` to run daily (Windows Task Scheduler or cron).

### Mentor score
Every metric is shown beside the combined score. A metric with no data shows "–" and is left out, with the remaining weights rescaled, so
missing data never counts as 0% or 100%. A mentor is ranked only after enough tests were due in the period.

| Metric | Formula | Weight |
|---|---|:---:|
| Tests conducted | completed ÷ due (cancelled and missed count against) | 30 |
| Marks entered | tests with marks for every active student ÷ completed tests | 20 |
| Schedule compliance | batches within their interval ÷ active batches | 20 |
| Tasks done | completed ÷ assigned in the period | 15 |
| Tasks on time | finished by deadline ÷ tasks with a deadline that are finished or overdue | 15 |

## Configuration

Thresholds live in `config/settings.py`:

| Setting | Default | Meaning |
|---|:---:|---|
| `TF_ATTENTION_THRESHOLD` | 50 | Student average (%) below which a student is flagged |
| `TF_MARKS_GRACE_DAYS` | 2 | Days after a test in which marks must be entered |
| `TF_MIN_TESTS_FOR_RANKING` | 3 | Tests due in the period before a mentor is ranked |
| `TF_MIN_BATCH_SAMPLE` | 3 | Students with results before a batch average is shown |
| `TF_MAX_UPLOAD_MB` | 2 | Maximum profile image size |
| `TF_ALERT_SYNC_SECONDS` | 300 | How often alerts re-evaluate on page loads |

Environment variables: `TESTFLOW_DEBUG` (`1` or `0`), `TESTFLOW_SECRET_KEY`, `TESTFLOW_ALLOWED_HOSTS`, and
`TESTFLOW_DB=postgres` with `TESTFLOW_DB_NAME`, `_USER`, `_PASSWORD`, `_HOST`, `_PORT`.

## Testing

```bash
python manage.py test
```
The suite covers login and role redirects, direct-URL access control, the temporary-password flow, mentor data scoping, marks rules and
constraints, alert de-duplication, mentor and student metrics, profile self-service, and a render of every page with and without data.

## Project structure

```
config/      Django settings and root URLs
accounts/    Custom user model, authentication, profile, Admin Control Center
portal/      Domain models, analytics.py (all metrics), services.py (status changes and alerts),
             views/ (one module per area), management commands (sync_alerts, seed_demo)
templates/   Shared layout, partials and pages
static/      CSS and JavaScript
tests/       Automated tests
```

## Deployment notes

The development server is for local use. Before exposing TestFlow to a wider audience: set `TESTFLOW_DEBUG=0`, provide a strong
`TESTFLOW_SECRET_KEY` and `TESTFLOW_ALLOWED_HOSTS`, serve over HTTPS, move to PostgreSQL, configure media storage for profile images,
and run `collectstatic`. Back up the database and the `media/` folder regularly.

## Roadmap

- [ ] CSV import of students and results from the LMS
- [ ] PDF export of reports
- [ ] Reminders for upcoming tests
- [ ] Management announcements
- [ ] Login rate limiting
- [ ] Bundled (offline) Chart.js
- [ ] Option for mentors to add students to their own batches

## License

No license has been specified yet. Add a `LICENSE` file before sharing the code publicly.
