"""Hiring multi-agent crew.

Six CrewAI agents emitting a ``FlatEnvelope`` per handoff. CrewAI's
``Task.context`` chains the FlatEnvelopes together; the hiring flow's
task_callback applies ``ForwardingEnforcer`` between tasks so each
downstream agent only sees the prior agent's ``semantic_payload`` --
never the raw artifacts.

LLM injection: the ``@CrewBase`` decorator does not tolerate a custom
``__init__``, so LLMs are read from class-level slots
(``HiringCrew.llm_classifier`` / ``HiringCrew.llm_content``). Callers can
swap them before instantiating the crew (see ``llm_mock.py`` and
``agent.flows.hiring_flow``).
"""

from __future__ import annotations

from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from jhcontext.flat_envelope import FlatEnvelope


def _default_classifier_llm() -> Any:
    from agent.libs.llms import llm_classifier_claude
    return llm_classifier_claude


def _default_content_llm() -> Any:
    from agent.libs.llms import llm_content_claude
    return llm_content_claude


def install_llms(classifier: Any | None = None, content: Any | None = None) -> None:
    """Override the crew's LLMs before instantiation.

    Pass a single object to ``classifier`` to use the same LLM everywhere
    (typical for tests + offline reproduction).
    """
    HiringCrew.llm_classifier = classifier if classifier is not None else _default_classifier_llm()
    HiringCrew.llm_content = content if content is not None else (
        classifier if classifier is not None else _default_content_llm()
    )


@CrewBase
class HiringCrew:
    """Six-agent hiring pipeline; each task outputs a ``FlatEnvelope``."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # LLM slots; set via install_llms() or read on first access.
    llm_classifier: Any | None = None
    llm_content: Any | None = None

    # ---- Agents ----------------------------------------------------------
    @agent
    def sourcing_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["sourcing_agent"],
            verbose=False,
            llm=self.llm_classifier or _default_classifier_llm(),
        )

    @agent
    def parsing_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["parsing_agent"],
            verbose=False,
            llm=self.llm_classifier or _default_classifier_llm(),
        )

    @agent
    def screening_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["screening_agent"],
            verbose=False,
            llm=self.llm_classifier or _default_classifier_llm(),
        )

    @agent
    def interview_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["interview_agent"],
            verbose=False,
            llm=self.llm_classifier or _default_classifier_llm(),
        )

    @agent
    def ranking_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["ranking_agent"],
            verbose=False,
            llm=self.llm_content or _default_content_llm(),
        )

    @agent
    def decision_support_agent(self) -> Agent:
        return Agent(
            config=self.agents_config["decision_support_agent"],
            verbose=False,
            llm=self.llm_content or _default_content_llm(),
        )

    # ---- Tasks (every task outputs a FlatEnvelope) -----------------------
    @task
    def sourcing_task(self) -> Task:
        return Task(
            config=self.tasks_config["sourcing_task"],
            output_pydantic=FlatEnvelope,
        )

    @task
    def parsing_task(self) -> Task:
        return Task(
            config=self.tasks_config["parsing_task"],
            context=[self.sourcing_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def screening_task(self) -> Task:
        return Task(
            config=self.tasks_config["screening_task"],
            context=[self.parsing_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def interview_task(self) -> Task:
        return Task(
            config=self.tasks_config["interview_task"],
            context=[self.screening_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def ranking_task(self) -> Task:
        return Task(
            config=self.tasks_config["ranking_task"],
            context=[self.screening_task(), self.interview_task()],
            output_pydantic=FlatEnvelope,
        )

    @task
    def decision_support_task(self) -> Task:
        return Task(
            config=self.tasks_config["decision_support_task"],
            context=[self.ranking_task()],
            output_pydantic=FlatEnvelope,
        )

    # ---- Crew ------------------------------------------------------------
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )
