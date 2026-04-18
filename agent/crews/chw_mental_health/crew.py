"""CHW Mental-Health Screening crews.

Three AI agents (interview-assistance, risk-classification, referral)
plus a supervisor-review oversight crew (district specialist) and an
audit crew. The "fourth agent" from paper §5.3 is the human supervisor
review, which is captured as a PROV Activity outside the clinical crew
so ``verify_temporal_oversight`` can validate it.
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
class CHWMentalHealthClinicalCrew:
    """3 AI agents: interview assistance → risk classification → referral."""

    agents_config = "config/clinical_agents.yaml"
    tasks_config = "config/clinical_tasks.yaml"

    @agent
    def interview_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["interview_agent"],
            verbose=True, llm=llm_data_claude,
        )

    @agent
    def risk_classifier_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_classifier_agent"],
            verbose=True, llm=llm_classifier_claude,
        )

    @agent
    def referral_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["referral_agent"],
            verbose=True, llm=llm_content_claude,
        )

    @task
    def interview_task(self) -> Task:
        return Task(
            config=self.tasks_config["interview_task"],
            output_pydantic=FlatEnvelope,
        )

    @task
    def risk_classification_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_classification_task"],
            context=[self.interview_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def referral_task(self) -> Task:
        return Task(
            config=self.tasks_config["referral_task"],
            context=[self.risk_classification_task()],
            output_pydantic=FlatEnvelope,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents, tasks=self.tasks,
            process=Process.sequential, verbose=True,
        )


@CrewBase
class CHWMentalHealthOversightCrew:
    """District specialist asynchronous review crew."""

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
class CHWMentalHealthAuditCrew:
    """Compliance audit crew."""

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
