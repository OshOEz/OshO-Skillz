---
number: 1
id: "un-audit-mantis-garde-sa-version-de-mant"
title: "Un audit Mantis garde sa version de Mantis jusqu'au bout"
date: "2026-11-21"
state: "accepted"
origin: "ticket"
origin_ref: "OSH-2"
pages: []
tickets: ["OSH-2"]
documents: []
supersedes: []
superseded_by: null
changes: []
accepted_at: "2026-11-26T23:49:23+01:00"
accepted_by: "OshOEz"
---

## Contexte

Un audit repris après une coupure relisait mantis.lock : si le pin avait bougé entre-temps, ou si /mantis-update avait repointé la copie partagée ~/.local/share/mantis, l'audit changeait de version de Mantis en cours de route.

## Décision

state.json garde mantis_commit (le commit du départ) ; la reprise appelle mantis_source.py ensure --commit <ce commit>. /mantis-update analyse sur un clone temporaire et ne touche plus la copie partagée. Une réponse de revue arrivée après la fusion d'un ticket part dans un ticket de suite (create_ticket).

## Conséquences

Un audit est cohérent d'une étape à l'autre ; /mantis-update refait un clone à chaque analyse (quelques secondes de réseau). Les audits commencés avant reçoivent mantis_commit à leur prochaine reprise.
