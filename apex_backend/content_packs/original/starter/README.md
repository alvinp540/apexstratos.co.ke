# ApexStratos starter assessments

These original Software Development assessments provide one published entry in
each student library. They are a small starter set, not completion of the
2,160-assessment content target. The content has not been reviewed by a human
subject-matter expert.

From `apex_backend`, validate without writing:

```powershell
python manage.py seed_apexstratos_starter_libraries
```

Append and publish the validated records in the configured development
database:

```powershell
python manage.py seed_apexstratos_starter_libraries --apply
python manage.py audit_apexstratos_inventory
```

The seed command is idempotent, validates all three packs before writing, and
uses the existing append-only assessment importer and publication checks.
Tutorials and Sponsored View can start Monday through Thursday in East Africa
Time; Sponsored View still requires verified KSh 20 payment. Main Contest can
start Friday through Sunday and still requires verified contest access. The
seed command does not grant payment entitlements.
