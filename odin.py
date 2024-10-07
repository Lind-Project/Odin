import time
import requests
import docker
import logging
from datetime import datetime

GITHUB_TOKEN = ''
GITHUB_ORG = 'Lind-Project'
POLL_INTERVAL = 300  # Poll every 60 seconds
MIN_IDLE_TIME = 300  # Minimum idle time before scaling down (in seconds)
GITHUB_ORG_FULL = 'https://github.com/Lind-Project'
CONTAINER_PREFIX = 'self-hosted-runner-container'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("odin.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

headers = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

client = docker.from_env()

def get_repos():
    # Get all repositories in the organization
    url = f'https://api.github.com/orgs/{GITHUB_ORG}/actions/permissions/repositories'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    repos = response.json()
    repo_names = [{"name": repo['name'], "owner": repo['owner']} for repo in repos["repositories"]]
    return repo_names

def get_queued_jobs(repo):
    # Get all workflows for all repositories in the organization
    url = f'https://api.github.com/repos/{GITHUB_ORG}/{repo["name"]}/actions/runs?status=queued'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    runs = response.json()['workflow_runs']
    queued_jobs = runs
    return queued_jobs

def get_self_hosted_runners():
    # Get all self-hosted runners at the organization level
    url = f'https://api.github.com/orgs/{GITHUB_ORG}/actions/runners'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    runners = response.json()['runners']
    return runners

def create_registration_token():
    # Create a registration token for the self-hosted runner
    url = f'https://api.github.com/orgs/{GITHUB_ORG}/actions/runners/registration-token'
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    token = response.json()['token']
    return token

def scale_up():
    logger.info("Scaling up...")
    try:
        token = create_registration_token()
        print(token)
        container = client.containers.run(
            "securesystemslab/lind_ubuntu:lind_ci",  # Image name
            command="bash -c './config.sh --unattended --ephemeral --url $GITHUB_ORG --token $GITHUB_TOKEN && ./run.sh'",  # Command to run
            detach=True,  # Run container in the background
            tty=True,  # Allocate a pseudo-TTY (equivalent to -t)
            stdin_open=True,  # Keep STDIN open (equivalent to -i)
            volumes={"/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"}},  # Mount /var/run/docker.sock
            privileged=True,  # Run in privileged mode
            ipc_mode="host",  # Use host's IPC namespace
            init=True,  # Run an init inside the container
            cap_add=["SYS_PTRACE"],  # Add the SYS_PTRACE capability
            labels={"self-hosted-runner": "true"},
            environment={
                "GITHUB_TOKEN": token,
                "GITHUB_ORG": GITHUB_ORG_FULL
                # Add any other environment variables your runner needs
            },
            name=CONTAINER_PREFIX + token,
            auto_remove=True  # Automatically remove the container when it exits
        )
        logger.info(f"Container {container.name} started successfully.")
    except Exception as e:
        logger.error(f"Error in scaling up: {e}")

def scale_down():
    logger.info(f"Terminating runners ...")
    # List all containers with the specified name prefix and "exited" status
    containers = client.containers.list(all=True, filters={
        "name": CONTAINER_PREFIX,
        "status": "exited"
    })
    if not containers:
        logger.info(f"No exited containers found with the name prefix: {CONTAINER_PREFIX}")
        return

    # Stop and remove each container found
    for container in containers:
        logger.info(f"Removing exited container: {container.name} ({container.id})")
        container.remove()
        logger.info(f"Container {container.name} ({container.id}) removed successfully.")


def manage_runners():
    while True:
        repo_names = get_repos()
        for repo in repo_names:
            logger.info(f"Checking repo: {repo['name']}")
            queued_jobs = get_queued_jobs(repo)
            runners = get_self_hosted_runners()

            logger.info(f"Queued jobs: {len(queued_jobs)}")
            logger.info(f"Self-hosted runners: {len(runners)}")

            if len(queued_jobs):
                for job in queued_jobs:
                    logger.info(f"Queued job: {job['name']} ({job['id']})")
                    scale_up()
        
        time.sleep(POLL_INTERVAL)
        scale_down()

if __name__ == "__main__":
    manage_runners()
