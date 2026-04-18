"""Chronic-Disease Remote Monitoring crews.

Four-agent clinical pipeline (sensor-aggregation → trend-analysis →
alert-generation → care-plan), plus an oversight crew (community nurse)
and an audit crew.
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
class ChronicMonitoringClinicalCrew:
    """4-agent pipeline: sensor → trend → alert → care-plan."""

    agents_config = "config/clinical_agents.yaml"
    tasks_config = "config/clinical_tasks.yaml"

    @agent
    def sensor_aggregation_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sensor_aggregation_agent"],
            verbose=True, llm=llm_data_claude,
        )

    @agent
    def trend_analysis_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["trend_analysis_agent"],
            verbose=True, llm=llm_classifier_claude,
        )

    @agent
    def alert_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["alert_agent"],
            verbose=True, llm=llm_classifier_claude,
        )

    @agent
    def care_plan_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["care_plan_agent"],
            verbose=True, llm=llm_content_claude,
        )

    @task
    def sensor_aggregation_task(self) -> Task:
        return Task(
            config=self.tasks_config["sensor_aggregation_task"],
            output_pydantic=FlatEnvelope,
        )

    @task
    def trend_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["trend_analysis_task"],
            context=[self.sensor_aggregation_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def alert_task(self) -> Task:
        return Task(
            config=self.tasks_config["alert_task"],
            context=[self.trend_analysis_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def care_plan_task(self) -> Task:
        return Task(
            config=self.tasks_config["care_plan_task"],
            context=[self.alert_task()],
            output_pydantic=FlatEnvelope,
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents, tasks=self.tasks,
            process=Process.sequential, verbose=True,
        )


@CrewBase
class ChronicMonitoringOversightCrew:
    """Community nurse weekly review crew."""

    agents_config = "config/oversight_agents.yaml"
    tasks_config = "config/oversight_tasks.yaml"

    @agent
    def nurse_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["nurse_agent"],
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
class ChronicMonitoringAuditCrew:
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
