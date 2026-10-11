# execution/tool_router.py
from repository_intelligence.workspace import Workspace, WorkspaceType

class ToolRouter:
    def build_command(self, workspace: Workspace, tool_action: str) -> list[str]:
        """
        Builds the correct command list for a specific tool action on a workspace type.
        """
        commands = {
            WorkspaceType.NODE: {
                "test": ["npm", "test"],
                "build": ["npm", "run", "build"]
            },
            WorkspaceType.JAVA_MAVEN: {
                "test": ["mvn", "test", "-q", "--no-transfer-progress"],
                "build": ["mvn", "compile"]
            },
            WorkspaceType.JAVA_GRADLE: {
                "test": ["./gradlew", "test"],
                "build": ["./gradlew", "build"]
            },
            WorkspaceType.PYTHON: {
                "test": ["pytest"],
                "build": []
            }
        }
        
        ws_cmds = commands.get(workspace.type)
        if not ws_cmds or tool_action not in ws_cmds:
            raise KeyError(f"No command mapping found for action '{tool_action}' in workspace type '{workspace.type}'")
            
        return ws_cmds[tool_action]
