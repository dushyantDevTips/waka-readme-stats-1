from base64 import b64decode
from re import sub

from github import Github, AuthenticatedUser, Repository, ContentFile, InputGitAuthor, UnknownObjectException

from manager_environment import EnvironmentManager as EM
from manager_download import DownloadManager as DM
from manager_debug import DebugManager as DBM


def init_github_manager():
    """
    Initialize GitHub manager.
    Current user, user readme repo and readme file are downloaded.
    """
    GitHubManager.prepare_github_env()
    DBM.i(f"Current user: {GitHubManager.USER.login}")


class GitHubManager:
    USER: AuthenticatedUser
    REPO: Repository
    _README: ContentFile
    _README_CONTENTS: str

    _START_COMMENT = f"<!--START_SECTION:{EM.SECTION_NAME}-->"
    _END_COMMENT = f"<!--END_SECTION:{EM.SECTION_NAME}-->"
    _README_REGEX = f"{_START_COMMENT}[\\s\\S]+{_END_COMMENT}"

    @staticmethod
    def prepare_github_env():
        """
        Download and store for future use:
        - Current GitHub user.
        - Named repo of the user [username]/[username].
        - README.md file of this repo.
        - Parsed contents of the file.
        """
        github = Github(EM.GH_TOKEN)
        GitHubManager.USER = github.get_user()
        GitHubManager.REPO = github.get_repo(f"{GitHubManager.USER.login}/{GitHubManager.USER.login}")
        GitHubManager._README = GitHubManager.REPO.get_readme()
        GitHubManager._README_CONTENTS = str(b64decode(GitHubManager._README.content), "utf-8")

    @staticmethod
    def _generate_new_readme(stats: str) -> str:
        """
        Generates new README.md file, inserts its contents between start and end tags.

        :param stats: contents to insert.
        :returns: new README.md string.
        """
        readme_stats = f"{GitHubManager._START_COMMENT}\n{stats}\n{GitHubManager._END_COMMENT}"
        return sub(GitHubManager._README_REGEX, readme_stats, GitHubManager._README_CONTENTS)

    @staticmethod
    def _get_author() -> InputGitAuthor:
        """
        Gets GitHub commit author specified by environmental variables.
        It is the user himself or a 'readme-bot'.

        :returns: Commit author.
        """
        if EM.COMMIT_BY_ME:
            return InputGitAuthor(GitHubManager.USER.login or EM.COMMIT_USERNAME, GitHubManager.USER.email or EM.COMMIT_EMAIL)
        else:
            return InputGitAuthor(EM.COMMIT_USERNAME or "readme-bot", EM.COMMIT_EMAIL or "41898282+github-actions[bot]@users.noreply.github.com")

    @staticmethod
    def branch() -> str:
        """
        Gets name of branch to commit to specified by environmental variables.
        It is the default branch (regularly, 'main' or 'master') or a branch specified by user.

        :returns: Commit author.
        """
        return GitHubManager.REPO.default_branch if EM.BRANCH_NAME == "" else EM.BRANCH_NAME

    @staticmethod
    def update_readme(stats: str) -> bool:
        """
        Updates readme with given data if necessary.
        Uses commit author, commit message and branch name specified by environmental variables.

        :param stats: Readme stats to be pushed.
        :returns: whether the README.md file was updated or not.
        """
        DBM.i("Updating README...")
        new_readme = GitHubManager._generate_new_readme(stats)
        if new_readme != GitHubManager._README_CONTENTS:
            GitHubManager.REPO.update_file(
                path=GitHubManager._README.path,
                message=EM.COMMIT_MESSAGE,
                content=new_readme,
                sha=GitHubManager._README.sha,
                branch=GitHubManager.branch(),
                committer=GitHubManager._get_author(),
            )
            DBM.g("README updated!")
            return True
        else:
            DBM.w("README update not needed!")
            return False

    @staticmethod
    async def push_to_pr(stats: str):
        """
        Pushes readme data to current PR body instead of committing it.

        :param stats: Readme stats to be pushed.
        """
        prefix = "README stats current output:"
        DBM.i("Commenting PR...")

        github = Github(EM.CURRENT_GITHUB_ACTION_TOKEN)
        pull_request = github.get_repo("anmol098/waka-readme-stats").get_pull(EM.PR_NUMBER)
        for comment in [ic for ic in pull_request.get_issue_comments() if ic.body.startswith(prefix)]:
            await DM.get_remote_graphql("hide_outdated_comment", use_github_action=True, id=comment.id)

        pull_request.create_issue_comment(f"{prefix}\n\n{stats}")
        DBM.g("PR commented!")

    @staticmethod
    def update_chart(chart_path: str):
        """
        Updates lines of code chart.
        Uses commit author, commit message and branch name specified by environmental variables.

        :param chart_path: path to saved lines of code chart.
        """
        DBM.i("Updating lines of code chart...")
        with open(chart_path, "rb") as input_file:
            data = input_file.read()
        try:
            contents = GitHubManager.REPO.get_contents(chart_path)
            GitHubManager.REPO.update_file(contents.path, "Charts Updated", data, contents.sha, committer=GitHubManager._get_author())
            DBM.g("Lines of code chart updated!")
        except UnknownObjectException:
            GitHubManager.REPO.create_file(chart_path, "Charts Added", data, committer=GitHubManager._get_author())
            DBM.g("Lines of code chart created!")
