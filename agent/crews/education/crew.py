"""Education fair assessment crew — 4 agents for Article 13 non-discrimination."""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class EducationIngestionCrew:
    """Essay ingestion and identity separation crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def ingestion_agent(self) -> Agent:
        return Agent(config=self.agents_config["ingestion_agent"], verbose=True)

    @task
    def ingestion_task(self) -> Task:
        return Task(config=self.tasks_config["ingestion_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class EducationGradingCrew:
    """Blind grading crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def grading_agent(self) -> Agent:
        return Agent(config=self.agents_config["grading_agent"], verbose=True)

    @task
    def grading_task(self) -> Task:
        return Task(config=self.tasks_config["grading_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class EducationEquityCrew:
    """Equity reporting crew (isolated workflow)."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def equity_agent(self) -> Agent:
        return Agent(config=self.agents_config["equity_agent"], verbose=True)

    @task
    def equity_task(self) -> Task:
        return Task(config=self.tasks_config["equity_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class EducationAuditCrew:
    """Education compliance audit crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def audit_agent(self) -> Agent:
        return Agent(config=self.agents_config["audit_agent"], verbose=True)

    @task
    def audit_task(self) -> Task:
        return Task(config=self.tasks_config["audit_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)
