#	Must-Pass Criterion	Source Section	"Vendor Response
(Yes / Partial / No)"
			
1	Production references at comparable scale	Company & Vendor Viability	
2	Dedicated AI research organization	Company & Vendor Viability	
3	Observability stack coverage in GA	Integration Coverage	
4	Infrastructure coverage including non-Kubernetes	Integration Coverage	
5	Cross-tool correlation demonstrated	Integration Coverage	
6	Raw telemetry stays in your environment	Security & Compliance	
7	SOC 2 Type II current report available	Security & Compliance	
8	Hypothesis revision when the first hypothesis is wrong	Use Cases (Incidents)	


Overall:

AI agents for production systems					
Section	Capability	Feature	Description	"Vendor Response
(Yes / Partial / No)"	Notes / Evidence
					
USE CASES					
	On-call and alerts	Autonomous alert triage	Every alert is assessed as it fires, 24/7, with a severity read and a recommended path: silence, run a predefined action, route to the right team, or escalate to investigation.		
		Triage Mode (fast impact assessment)	A first-responder pass, typically under five minutes, answering the questions an on-call engineer checks first: is this a blip or sustained, how often it fires, single pod or multi-pod, low-traffic window. Stops once answered, with no exploratory root-cause analysis unless asked.		
		Adaptive Mode (agent-decided depth)	Starts with triage, then the agent evaluates its own findings and decides whether to stop or auto-escalate to a deep investigation, matching effort to severity without human intervention.		
		Runbook-guided triage	Encodes the checks an on-caller would run (active maintenance window, last deploy for the service, specific log queries, affected-user counts, downstream dependency traces) and the agent follows them during triage.		
		Configurable escalation policy	Teams define what counts as high-impact, which alerts always escalate, and which never go beyond triage automatically. A human can always escalate manually, and escalation is never solely the agent's call.		
		Alert enrichment	Each alert arrives with context and an initial hypothesis before the engineer is paged, so an engineer starts with a head start rather than a blank page.		
		Signal-to-noise consolidation	Cascading alerts across multiple services collapse into one incident story that preserves causal order and separates the primary cause from downstream symptoms.		
		Noise detection and tuning	Flags noisy alerts for tuning and surfaces the common root cause behind repeat alert classes, pointing toward a fix that reduces alert volume over time.		
	Incidents	Swarm of specialized agents	A team of domain-specialized agents investigates in parallel, each pursuing different hypotheses from different starting points, rather than one agent reasoning sequentially.		
		Specialized agents per domain	Distinct agents tuned for distinct investigation domains rather than one general agent running different prompts, so each reasons with depth in its area.		
		Independent verification	A verifier validates findings against production evidence, not logical coherence, before they surface.		
		Dynamic tool calls	The agent decides on the fly which tool to use and which query to write, and reformulates when results come back wrong, rather than following a fixed query sequence.		
		Hypothesis revision	When evidence contradicts the current path, the investigation branches and pursues alternatives instead of restarting or stalling without a matching playbook.		
		Root cause with cited evidence	Surfaces working theories backed by production evidence, with every claim linked to an artifact: a log line, metric, trace, or code diff.		
		First-team-right routing	When a root cause lives outside the paged team's domain, the incident routes to the correct owner on the first pass rather than after several hops.		
		Incident channel context capture	In Slack incident channels, ingests messages, links, and logs and classifies them into symptoms, human findings, impact updates, and evidence to reason about the incident as it unfolds.		
		Proactive evidence-backed posting	Posts new, specific, evidence-backed findings to the channel without being mentioned, surfacing signals not already discussed (beta, Slack).		
		Catch-up summaries for new joiners	Sends a new participant a private summary of what has happened so far, visible only to them.		
		Postmortem generation	Drafts a postmortem from the channel activity and investigation timeline, ready to paste into Google Docs, Notion, Jira, or Linear. See the UI section for the Workbench collaboration experience.		
	Production tasks	Deployment monitoring	Watches every rollout for anomalies and begins investigating before they become alerts.		
		Scheduled and triggered workflows	Agents run on a cadence or fire on production triggers, pre-investigating items so the priority feed is populated with verified findings before the engineer opens it.		
		Operational reporting	Generates routine artifacts on a schedule: SLO reports, on-call handovers, change-risk briefs, and incident write-ups.		
		Regression and anomaly lead time	Catches regression classes before they page, giving advance warning measured in minutes or hours.		
		Template library	A library of pre-built workflow templates to start from rather than configuring each workflow from scratch.		
	Conversational production queries	Natural language production access	Any engineer, not just on-call, can query production in plain language to debug, run analyses, or get context, without source code or runbook exposure required.		
		On-call prep and handoff summaries	Compiles current telemetry, active alerts, recent changes, and relevant incident history into a shift brief, and produces investigation state so the next engineer does not restart.		
		Internal terminology mapping	Maps your team's service names, product terms, and jargon to the correct services, metrics, and logs, maintaining context across a multi-turn investigation.		
PLATFORM					
	Models	Domain-specialized post-trained models	Models post-trained for reasoning over fragmented telemetry and causal chains across heterogeneous production signals.		
		Managed frontier models	Frontier models managed and paired with the specialized models, so the platform draws on both.		
		Per-task model selection	Picks the best model for the specific task at hand: image analysis, deterministic tasks, reasoning, and others.		
		Orchestration across model releases	Absorbs the orchestration changes that come with each new model release, so behavior stays stable as models update.		
	Context	Persistent knowledge graph	A queryable model of services, dependencies, deploy history, configuration, runbooks, and incident timelines that investigations reason over.		
		Real-time updates	Updates as topology and the production system change, rather than a one-time ingest or a manual refresh cycle.		
		Knowledge graph auditability	Teams can inspect what the system believes, correct errors, and see how its understanding of the environment is built over time.		
		Implicit learning	Improves from engineer corrections without manual retraining sprints, so patterns discovered during one incident reduce toil in future cases.		
	Actions	Alert actions	Silences or snoozes alerts, executes predefined actions on an alert, and routes to the right team, directly from triage.		
		Remediation actions	Reverts commits, opens PRs, executes GitHub Actions workflows, and runs config changes, triggered from a confirmed finding.		
		Read and write across the stack	Queries logs, traces, metrics, and changelogs as read operations, and issues write operations such as rollbacks and config changes when approved, across connected tools.		
		Guardrailed execution	Every action runs within defined boundaries. Outside those boundaries Resolve recommends but does not act. The autonomy envelope widens as trust grows.		
		Approval workflows	Write actions require engineer approval before execution, with the proposed action, request, execution, and impact verification all captured.		
		Outcome verification	After executing, the system verifies the action had the intended effect rather than assuming success.		
		Full action audit trail	Every action and the reasoning behind it is logged and auditable per investigation.		
	Scalability	Concurrent investigation handling	Handles many parallel investigations and high log volumes without degradation.		
		Schema-change adaptation	Adapts to log and telemetry schema changes mid-run without a manual retraining sprint or broken parsers.		
		Rapid team and service onboarding	Adds a new team and service without vendor professional services, in a single day.		
UI					
	collaborative investigation IDE	Shared investigation surface	Engineers and agents investigate on the same evidence on a shared surface.		
		Real-time visibility	A real-time view into hypotheses being pursued, evidence gathered, and work in progress.		
		Per-agent work review	Engineers see each agent's work and review the evidence it gathered, rather than receiving a summary-only output.		
		Evidence and hypothesis exploration	Explore evidence and hypotheses without losing or switching context, while the main investigation continues.		
		Private parallel investigations	Run a private investigation thread alongside the agent while the main investigation proceeds.		
		Investigation steering	Redirect the investigation mid-flight, and the agent preserves context and cites the reason for the pivot.		
		Teammate tag-in	Tag teammates into the investigation and bring them into the conversation with shared state.		
	Chat surfaces	Slack-native workflow	Findings posted to incident channels, with engineers able to redirect the investigation from Slack.		
		MS Teams (beta)	Available in MS Teams for capturing incident context and answering questions in-channel.		
		CLI and web	Available through a command-line interface and a web interface.		
		Natural language from any surface	Query production in natural language from any supported surface, with context maintained across turns.		
EXTENSIBILITY					
	Building	Resolve in your agents (MCP server)	Available as an MCP server so your own agents and coding tools (for example Cursor or Claude Code) call into Resolve's capabilities while keeping your existing workflows.		
		Public API	A public API for programmatic access to Resolve's capabilities from your own systems.		
		Your skills in Resolve	Codify your team's expertise as composable Skills that Resolve's managed agents consume.		
		Build custom agents	Build your own investigation agents on the platform (models, context graph, governed actions, integrations) rather than only using the managed agents.		
INTEGRATION COVERAGE					
	Coverage and correlation	Observability stack coverage	Connects to your specific observability tools in general availability, correlating metrics, logs, and traces across them rather than reasoning over a single vendor's data.		
		Infrastructure coverage	Operates across Kubernetes, VMs, bare metal, cloud-native services, and non-containerized workloads, including the non-standard portions of a heterogeneous stack.		
		Code and repository coverage	Connects to code hosts to read source, diffs, and deployment history as part of investigation reasoning.		
		CI/CD and deployment coverage	Connects to CI/CD and deployment tooling to identify deploy events and correlate them to anomalies.		
		Incident management coverage	Connects to paging and incident tooling so investigations start automatically when an incident is declared.		
		Knowledge and documentation coverage	Makes runbooks, wikis, and internal repos accessible to the knowledge graph so investigations draw on team-specific context.		
		Cross-tool correlation	Traces a symptom in one tool to a root cause in a different tool, building one coherent narrative across observability, CI/CD, infra state, and code without manual query construction.		
		Breadth of pre-built integrations	60+ pre-built integrations across the categories above, connecting without a custom connector build for each tool.		
		Heterogeneous-environment handling	Handles non-standard stacks (VM infrastructure alongside Kubernetes, Graphite alongside Prometheus, custom deployment tooling) without vendor professional services per integration.		
ONBOARDING & TIME TO VALUE					
	Time to value	Plug-and-play start	Connects to your stack and begins delivering value without a lengthy services-led implementation.		
		Continuous learning built in	Every investigation improves the next, so the system gets better in your environment over the deployment window without engineering effort.		
		No per-team professional services	New teams and services onboard without requiring vendor professional services for each integration.		
		Self-service onboarding	Teams reach value with limited effort through self-service setup.		
	Adoption support	Forward-deployed engineers (FDEs)	Forward-deployed engineers work alongside your team to accelerate setup, integration, and early investigations in your environment.		
		AI engagement managers	AI engagement managers drive adoption, help expand usage across teams, and translate early wins into broader rollout.		
SECURITY & COMPLIANCE					
	Data handling	Raw telemetry residency	Logs, metrics, and traces stay in your environment and are not stored in the vendor cloud.		
		In-VPC component (Satellite)	Integrations operate within your private network through an in-VPC component rather than requiring data to leave it.		
		Data egress scope documentation	Provides a data flow diagram showing what data moves, to what destination, and at what volume per investigation, rather than a verbal assurance.		
		Cloud egress cost transparency	Quantifies expected data transfer volume for your environment, relevant where egress carries a direct cost.		
		Data redaction	Sensitive data is redacted before reaching the vendor environment, with custom redaction rules configurable.		
		Tenant isolation	Cryptographically enforced isolation between your data and other customers' data.		
	Compliance and governance	Deployment options	SaaS, BYOC, or self-hosted deployment to match data residency requirements.		
		SOC 2 Type II	Current SOC 2 Type II report available, not a summary or a badge.		
		Additional compliance	GDPR, HIPAA, and PCI-DSS coverage for regulated environments. [Verify which certifications are current before sharing externally.]		
		RBAC and access control	Team-scoped role-based access control governing who can manage agent context and trigger actions.		
		Audit trails	Full action and reasoning audit trail per investigation.		
		Hierarchical guardrails	Org, team, and personal guardrail levels, where lower levels cannot override governance set above them.		
COMPANY & VENDOR VIABILITY					
	Vendor viability	Production references at scale	Reference customers at a comparable scale and compliance tier you can speak with, not just logos.		
		Customer expansion evidence	Existing customers adding teams or use cases beyond their initial pilot.		
		Dedicated AI research organization	A named research team doing domain-specific work on production operations, not general LLM engineering.		
		Post-trained models on production incident data	Models post-trained on real production incident data rather than a prompted foundation model.		
		Continuous evaluation infrastructure	Automated evals running across incident types to catch silent regression when foundation models update.		
		Model migration absorption	The vendor absorbs model and orchestration churn across its customer base rather than leaving it to your team.		
		Funding and team depth	Funding and team sufficient to sustain a multi-year platform investment as foundation models evolve.		
		Roadmap commitments	Specific roadmap commitments for the next two quarters.		