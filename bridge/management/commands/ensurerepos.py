from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.conf import settings
from bridge.mutations.repo import _create_github_repo
from bridge import inputs
from asgiref.sync import async_to_sync


async def create_github_repos(repos: dict):

    for repo_identifier in repos:
        input = inputs.CreateGithubRepoInput(
            identifier=repo_identifier, name=repo_identifier
        )

        try:
            await _create_github_repo(input, None)
        except Exception as e:
            print(f"Error creating repo {repo_identifier}: {e}")


class Command(BaseCommand):
    help = "Ensures that the repos are used"

    def handle(self, *args, **kwargs):
        repos = settings.ENSURED_REPOS

        async_to_sync(create_github_repos)(repos)
