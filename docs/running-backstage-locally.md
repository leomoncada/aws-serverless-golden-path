# Running Backstage locally against this template

**These steps have not been executed in this repository.** Nothing here has
been verified by actually running Backstage. `backstage/template.yaml` is
validated only against the scaffolder schema (`tests/test_backstage_template.py`),
which checks structure and that its parameters match `template/cookiecutter.json`
exactly. That is weaker than execution: it cannot catch a `fetch:cookiecutter`
run that fails because cookiecutter is not installed, a `publish:github`
step that fails without a GitHub token, or a subtly wrong Jinja/Nunjucks
expression. If you follow this guide and something does not work as written,
that is expected until someone runs it and files a correction.

This repository does not host Backstage. Standing up a portal costs money to
run and adds a dependency (Node, a full app scaffold) that the rest of the
golden path does not need. `make demo` never depends on Backstage; `make
portal` is a stub that points here.

## Why you would do this

To confirm that `backstage/template.yaml` actually scaffolds a working service
when driven from a real Backstage instance, not just that it satisfies the
scaffolder's JSON schema.

## Prerequisites

- Node.js (LTS) and a package manager (`npx`/`yarn`)
- A GitHub personal access token with repo-creation scope, if you want the
  `publish:github` step to run to completion
- Optionally, `cookiecutter` on `PATH`, or a Docker daemon (the cookiecutter
  scaffolder backend module can shell out to either)

No AWS account or credentials are needed for this part; the generated
service's own tests still run entirely against LocalStack.

## Steps (untested in this repo)

1. Scaffold a throwaway Backstage app:

   ```bash
   npx @backstage/create-app@latest --path ./backstage-app
   cd backstage-app
   ```

2. Add the cookiecutter scaffolder backend module, since `fetch:cookiecutter`
   is not built in:

   ```bash
   yarn --cwd packages/backend add @backstage/plugin-scaffolder-backend-module-cookiecutter
   ```

   Register it in `packages/backend/src/index.ts` alongside the other
   scaffolder modules, per that plugin's own README.

3. Point Backstage at this repository's template. The simplest option while
   iterating locally is to register it directly from a checkout, using
   `app-config.yaml`:

   ```yaml
   catalog:
     locations:
       - type: file
         target: ../aws-serverless-golden-path/backstage/template.yaml
         rules:
           - allow: [Template]
   ```

   (Adjust the relative path to wherever you cloned
   `aws-serverless-golden-path` next to `backstage-app`.)

4. Start Backstage:

   ```bash
   yarn dev
   ```

5. Open the app (default `http://localhost:3000`), go to "Create", and pick
   "AWS serverless service". The form should show exactly the fields declared
   in `backstage/template.yaml`'s `spec.parameters`: `service_name`,
   `owner_team`, `description`, `python_runtime`, `aws_region`. That is the
   same set `template/cookiecutter.json` declares; `test_parameters_match_cookiecutter_variables`
   in `tests/test_backstage_template.py` is what keeps the two in sync
   without a human checking by eye.

6. Run the scaffolder. If cookiecutter and a GitHub token are set up, this
   should generate a repository from `template/`, push it, and register it in
   the catalog. If either dependency is missing, the `fetch` or `publish`
   step will fail there rather than produce something silently wrong.

## What this does not prove

Even a successful run above proves the adapter works for one specific
Backstage version, one specific plugin version, and one specific set of
inputs. It does not replace running this in CI, which this repository does
not attempt, because that would mean hosting or spinning up Backstage on
every pull request for a component this repo treats as optional.
