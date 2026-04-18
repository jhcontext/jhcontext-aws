"""Rural Emergency Cardiac Triage crews.

Three-agent clinical pipeline (physio-signal → triage-classifier →
resource-allocator), plus an oversight crew (teleconsult cardiology
specialist) and an audit crew.
"""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from jhcontext.flat_envelope import FlatEnvelope

from agent.libs.llms import (
    llm_classifier_claude,
    llm_content_claude,
    llm_data_claude,
    llm_manager_claude,
)


@CrewBase
class TriageRuralClinicalCrew:
    """3-agent pipeline: physio-signal → triage → resource-allocation."""

    agents_config = "config/clinical_agents.yaml"
    tasks_config = "config/clinical_tasks.yaml"

    @agent
    def physio_signal_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["physio_signal_agent"],
            verbose=True, llm=llm_data_claude,
        )

    @agent
    def triage_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["triage_agent"],
            verbose=True, llm=llm_classifier_claude,
        )

    @agent
    def resource_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["resource_agent"],
            verbose=True, llm=llm_content_claude,
        )

    @task
    def physio_signal_task(self) -> Task:
        return Task(
            config=self.tasks_config["physio_signal_task"],
            output_pydantic=FlatEnvelope,
        )

    @task
    def triage_task(self) -> Task:
        return Task(
            config=self.tasks_config["triage_task"],
            context=[self.physio_signal_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def resource_task(self) -> Task:
        return Task(
            config=self.tasks_config["resource_task"],
            context=[self.triage_task()],
            output_pydantic=FlatEnvelope,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents, tasks=self.tasks,
            process=Process.sequential, verbose=True,
        )


@CrewBase
class TriageRuralOversightCrew:
    """Teleconsult cardiology specialist review."""

    agents_config = "config/oversight_agents.yaml"
    tasks_config = "config/oversight_tasks.yaml"

    @agent
    def specialist_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["specialist_agent"],
            verbose=True, llm=llm_content_claude,
        )

    @task
    def oversight_task(self) -> Task:
        return Task(config=self.tasks_config["oversight_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks,
                    process=Process.sequential, verbose=True)


@CrewBase
class TriageRuralAuditCrew:
    """Compliance audit narrative."""

    agents_config = "config/audit_agents.yaml"
    tasks_config = "config/audit_tasks.yaml"

    @agent
    def audit_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["audit_agent"],
            verbose=True, llm=llm_manager_claude,
        )

    @task
    def audit_task(self) -> Task:
        return Task(config=self.tasks_config["audit_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks,
                    process=Process.sequential, verbose=True)
