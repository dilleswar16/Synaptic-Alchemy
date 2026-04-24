# Corvin Product Overview

## What Corvin Is

Corvin is an Azure-native investigation platform designed for a personal project. It receives operational triggers, gathers evidence from Azure and application observability systems, investigates likely causes, produces a structured RCA, proposes a structured fix strategy, and later evolves toward approval-gated remediation and verification.

It is not a fork of Vishwakarma. It is a new product that borrows the strongest design ideas from that style of system while adapting them to a different cloud, different evidence plane, and a more explicit approval and execution path.

## Product Goal

The goal is to shorten the distance between an alert and a defensible response.

Instead of forcing an operator to pivot manually across Azure alerts, AKS, Elastic, APIM logs, deployment history, and application context, Corvin should:

1. ingest the trigger,
2. enrich it with high-signal evidence,
3. investigate the likely cause,
4. produce a structured RCA,
5. produce a justified fix strategy,
6. request human approval before any future execution,
7. eventually execute and verify changes in later versions.

## Target Users

- Primary user: the product owner building and operating the platform for personal use.
- Secondary users: platform engineers, SREs, or developers who want an investigation assistant over Azure-native infrastructure and Java Spring Boot services.

## What Corvin Monitors

- Java Spring Boot backend applications
- AKS workloads
- Azure API Management
- Azure-managed infrastructure that emits alerts
- Centralized logs and metrics stored in Elastic

## Control Plane Versus Monitored Applications

Corvin is the control plane, not the monitored business application.

- The monitored apps may be Java Spring Boot.
- The Corvin platform itself should be built in Python.
- The product must treat monitored workloads as external systems observed through adapters, not as part of its own runtime.

## Product Workflow

The target end-to-end workflow is:

Trigger -> Enrich -> Investigate -> RCA -> Fix Strategy -> Human Approval -> Execute Fix -> Verify -> Learn

Important interpretation:

- Investigate includes research, evidence gathering, correlation, and hypothesis testing.
- Fix Strategy is a recommended remediation plan, not the execution itself.
- Human Approval is mandatory before execution-capable versions perform any change.

## Version Philosophy

Corvin should be built and tested version by version.

- V1 focuses on Trigger, Enrich, Investigate, RCA, and Fix Strategy.
- V2 strengthens operator workflow, approval handling, and collaboration surfaces.
- V3 introduces approval-gated execution, verification, rollback handling, and stronger auditability.

## Product Thesis

The product's value comes from combining five things:

1. A strong trigger and enrichment layer.
2. A structured, configurable investigation engine.
3. Azure-aware and Elastic-aware evidence adapters.
4. A clean operator experience across CLI, API, web app, and Teams.
5. A controlled path from diagnosis to fix strategy to approved execution.

## Non-Goals For Early Versions

- Full autonomous remediation without approval.
- Giant one-shot end-to-end implementations that are hard to test.
- Hardcoded environment data scattered across source code.
- Designing around AWS assumptions.