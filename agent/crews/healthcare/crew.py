"""Healthcare compliance crew — 5 agents for Article 14 human oversight."""

from __future__ import annotations

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class HealthcareSensorCrew:
    """Sensor data collection crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def sensor_agent(self) -> Agent:
        return Agent(config=self.agents_config["sensor_agent"], verbose=True)

    @task
    def sensor_task(self) -> Task:
        return Task(config=self.tasks_config["sensor_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class HealthcareSituationCrew:
    """Situation recognition crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def situation_agent(self) -> Agent:
        return Agent(config=self.agents_config["situation_agent"], verbose=True)

    @task
    def situation_task(self) -> Task:
        return Task(config=self.tasks_config["situation_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class HealthcareDecisionCrew:
    """Treatment recommendation crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def decision_agent(self) -> Agent:
        return Agent(config=self.agents_config["decision_agent"], verbose=True)

    @task
    def decision_task(self) -> Task:
        return Task(config=self.tasks_config["decision_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class HealthcareOversightCrew:
    """Physician oversight simulation crew."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def oversight_agent(self) -> Agent:
        return Agent(config=self.agents_config["oversight_agent"], verbose=True)

    @task
    def oversight_task(self) -> Task:
        return Task(config=self.tasks_config["oversight_task"])

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class HealthcareAuditCrew:
    """Compliance audit crew."""

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
