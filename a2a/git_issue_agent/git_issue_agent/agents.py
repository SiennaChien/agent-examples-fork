from crewai import Agent, Crew, Process, Task
from git_issue_agent.config import Settings
from git_issue_agent.data_types import UserQueryJudgement
from git_issue_agent.llm import CrewLLM
from git_issue_agent.prompts import REPO_ID_BACKSTORY, TOOL_CALL_PROMPT
class GitAgents():
    
    def __init__(self, config: Settings, issue_tools):
        self.llm = CrewLLM(config)

        ###################
        # Pre-requisitie validator
        # ##################
        self.prereq_identifier = Agent(
            role="Pre-requisite Judge",
            goal="To determine whether a user has supplied enough information to find Github issues.",
            backstory=REPO_ID_BACKSTORY,
            verbose=True,
            llm=self.llm.llm
        )

        self.prereq_identifier_task = Task(
            description=(
                "User query: {request}"
            ),
            agent=self.prereq_identifier,
            output_pydantic=UserQueryJudgement,
            expected_output=(
                "A judgement on whether a request from a user successfully identifies an organization or user that owns issues."
            ),
        )

        self.prereq_id_crew = Crew(
            agents=[self.prereq_identifier],
            tasks=[self.prereq_identifier_task],
            process=Process.sequential,
            verbose=True,           
        )

        ###################
        # Issue Researcher
        # ##################
        self.issue_researcher = Agent(
            role="GitHub Issue Analyst",
            goal=(
                "Answer the user's query, using tools provided from MCP server. "
                "Prefer read-only operations. When querying, be explicit about repo owner/name and filters."
            ),
            backstory=TOOL_CALL_PROMPT,
            tools=issue_tools,
            verbose=True,
            llm=self.llm.llm,
            inject_date=True,
            max_iter=3
        )
            
        # --- A generic task template -------------------------------------------------
        # The agent will use MCP tools to fulfill natural-language queries.
        self.issue_query_task = Task(
            description=(
                "Retrieve Github issues using tool calls in order to answer the user's query.\n"
                "User query: {request}"
            ),
            agent=self.issue_researcher,
            expected_output=(
                "A direct answer to the user's query, citing the output of the tool to support your answer. Provide as many details as possible to support your claim."
            ),
        )

        self.crew = Crew(
            agents=[self.issue_researcher],
            tasks=[self.issue_query_task],
            process=Process.sequential,
            verbose=True,
        )