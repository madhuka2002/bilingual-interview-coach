# Local Jenkins on Windows Docker Desktop

This stack runs a Jenkins LTS controller on `http://127.0.0.1:8080` and a
separate Linux inbound agent containing uv and uv-managed Python 3.12. The
controller is not exposed beyond localhost, and the agent connects over
WebSocket, so no inbound agent port is published.

## Prerequisites

- Windows Docker Desktop using Linux containers
- Git repository hosted at a URL the Jenkins controller can reach

All commands below run from `ci/jenkins` in PowerShell.

## Start and unlock the controller

Build and start only the controller first; the agent needs a node secret that
does not exist yet.

```powershell
docker compose up --build -d controller
docker compose exec controller cat /var/jenkins_home/secrets/initialAdminPassword
```

Open `http://127.0.0.1:8080`, enter the initial password, and create the local
administrator. The image already contains the Pipeline, Git, and JUnit plugins,
so installing additional plugins is optional.

## Enroll the dedicated agent

1. Open **Manage Jenkins > Nodes > New Node**.
2. Name it `bilingual-interview-coach-linux`, select **Permanent Agent**, and
   create it with these settings:
   - Number of executors: `1`
   - Remote root directory: `/home/jenkins/agent`
   - Labels: `bic-python312-uv`
   - Usage: **Only build jobs with label expressions matching this node**
   - Launch method: **Launch agents by connecting it to the controller**
   - Enable **Use WebSocket** if Jenkins shows that option.
3. Save the node and open its status page. Copy the secret from the displayed
   agent launch command.
4. Copy `agent.env.example` to `agent.env`, replace the placeholder secret, and
   keep the node name synchronized with `JENKINS_AGENT_NAME`.
5. Build and start the agent:

```powershell
Copy-Item agent.env.example agent.env
# Edit agent.env and replace JENKINS_SECRET before continuing.
docker compose up --build -d agent
docker compose logs -f agent
```

`agent.env` is ignored by Git. Do not paste its secret into the compose file,
the Jenkinsfile, build logs, or job configuration.

## Create a Pipeline script from SCM job

1. From the Jenkins dashboard, select **New Item**, enter a job name, choose
   **Pipeline**, and select **OK**.
2. Under **Pipeline**, choose **Pipeline script from SCM**.
3. Select **Git**, enter the repository URL and credentials if required, and
   set **Branches to build** to the branch or revision selector to validate.
4. Keep **Script Path** as `Jenkinsfile`, save, and choose **Build Now**.

The Jenkinsfile disables the implicit checkout and calls `checkout scm`, so the
exact revision selected by the job is the revision tested. The job runs only on
the `bic-python312-uv` agent, installs the locked environment, checks Ruff lint
and formatting, publishes `reports/pytest.xml`, and audits locked dependencies.

## Operate or remove the local stack

```powershell
docker compose ps
docker compose logs -f controller agent
docker compose down
```

Named volumes retain controller configuration and the agent workspace across
normal `down`/`up` cycles. Add `--volumes` only when you intentionally want to
erase the local Jenkins configuration and agent workspace.
