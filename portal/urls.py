from django.urls import path
from django.views.generic import RedirectView

from . import views as v

urlpatterns = [
    path("management/", v.overview, name="overview"),                 # Admin + Management
    path("mentor/", v.workspace, name="workspace"),                   # Mentor workspace
    path("admin/", RedirectView.as_view(pattern_name="control_center", permanent=False)),

    path("mentors/", v.mentors_list, name="mentors_list"),
    path("mentors/<int:pk>/", v.mentors_detail, name="mentors_detail"),

    path("batches/", v.batches_list, name="batches_list"),
    path("batches/new/", v.batches_new, name="batches_new"),
    path("batches/<int:pk>/", v.batches_detail, name="batches_detail"),
    path("batches/<int:pk>/edit/", v.batches_edit, name="batches_edit"),
    path("batches/<int:pk>/reason/", v.batches_reason, name="batches_reason"),

    path("students/", v.students_list, name="students_list"),
    path("students/new/", v.students_new, name="students_new"),
    path("students/<int:pk>/", v.students_detail, name="students_detail"),
    path("students/<int:pk>/edit/", v.students_edit, name="students_edit"),

    path("assessments/", v.tests_list, name="tests_list"),
    path("assessments/new/", v.tests_new, name="tests_new"),
    path("assessments/<int:pk>/", v.tests_detail, name="tests_detail"),
    path("assessments/<int:pk>/edit/", v.tests_edit, name="tests_edit"),
    path("assessments/<int:pk>/action/", v.tests_action, name="tests_action"),
    path("assessments/<int:pk>/marks/", v.tests_marks, name="tests_marks"),

    path("tasks/", v.tasks_list, name="tasks_list"),
    path("tasks/new/", v.tasks_new, name="tasks_new"),
    path("tasks/<int:pk>/", v.tasks_detail, name="tasks_detail"),
    path("tasks/<int:pk>/edit/", v.tasks_edit, name="tasks_edit"),

    path("notifications/", v.notifications, name="notifications"),
    path("notifications/read-all/", v.notifications_read_all, name="notifications_read_all"),
    path("notifications/<int:pk>/read/", v.notifications_read, name="notifications_read"),
    path("notifications/<int:pk>/open/", v.notifications_open, name="notifications_open"),

    path("reports/", v.reports, name="reports"),
    path("reports/results.csv", v.reports_results, name="reports_results"),
    path("reports/tests.csv", v.reports_tests, name="reports_tests"),
    path("reports/mentors.csv", v.reports_mentors, name="reports_mentors"),
]
