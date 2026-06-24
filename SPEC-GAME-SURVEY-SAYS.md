# LocalPlay Survey Says Game Spec

## Overview

Add **Survey Says** as a team survey-answer game inspired by family feud formats. Players submit free-text guesses from their phones, while the host adjudicates close answers, reveals answer slots, tracks strikes, and advances rounds. The TV/spectator view shows the answer board, teams, current bank, and final podium.

```text
GameType: survey_says
Runtime family: team_survey
Backend engine: survey_says_engine.py
Frontend display name: Survey Says
Catalog category: Quiz/Trivia
AI marker: no in MVP
```

## Implementation Status

Status: standalone playable MVP implemented on June 24, 2026.

Implemented in this repo with:

- `backend/survey_says_engine.py` pure game mechanics, setup validation, team assignment, strikes, steals, scoring, late joins, and public/private sync.
- `game_type="survey_says"` room creation with default curated survey rounds.
- WebSocket runtime messages for player guesses, host answer reveals, strikes, reveal-all, next round, reconnect, spectator sync, and podium.
- `frontend/src/components/SurveySaysGame.tsx` shared organizer/player/spectator UI.
- Catalog/rules metadata so the game appears in standalone LocalPlay with rules access before play.
- Focused backend tests for validation, scoring, steal flow, public redaction, late join, and podium.

Current exposure is standalone LocalPlay first. Revelry/host-app exposure remains disabled until embedded policy rows and gamma QA are explicitly added.

## MVP Scope

- Minimum 2 players.
- Server automatically splits players into two teams by join order.
- Late joiners are assigned to the smaller team while the game is active.
- Host starts with curated default survey rounds.
- Each round has one question and 3-8 ranked answer slots with points.
- Players submit guesses from their phones.
- Host sees submitted guesses and chooses whether to reveal a matching answer or assign a strike.
- Three strikes move the round into steal mode for the other team.
- A successful steal awards the current bank to the stealing team.
- A failed steal awards the current bank to the original active team.
- Revealing all answers can end the round without awarding the bank when used as a host reveal.
- Host manually advances rounds.
- Final podium ranks teams by total score.

## Goals

- Add a familiar, team-based party game that scales to larger rooms.
- Keep live judgement with the host so close/free-text answers remain fun instead of brittle.
- Reuse LocalPlay's room, player, spectator, reconnect, and podium infrastructure.
- Support late party joins without restarting the room.
- Keep the first version simple enough to extend later with AI-generated survey packs.

## Non-Goals

- No real survey data source in MVP.
- No automatic fuzzy answer matching in live runtime; the host adjudicates.
- No buzzers or head-to-head faceoff in MVP.
- No AI generation or saved authoring UI in MVP.
- No Revelry exposure until standalone QA and host-app policy rollout.

## Game Rules

1. Players join the lobby.
2. LocalPlay splits players into Team A and Team B.
3. The host starts the first survey question.
4. The active team submits guesses from phones.
5. The host reveals matching answers on the board or gives a strike.
6. Revealed answer points go into the round bank.
7. If the active team reveals every answer, they win the bank.
8. If the active team reaches the strike limit, the other team gets one steal attempt.
9. A successful steal wins the bank for the stealing team.
10. A failed steal awards the bank to the original active team.
11. Teams alternate which team starts each round.
12. Final results rank teams by score.

## Setup

```json
{
  "game_type": "survey_says",
  "game_title": "Survey Says",
  "round_count": 5,
  "team_count": 2,
  "max_strikes": 3,
  "guess_time_seconds": 45,
  "allow_late_join": true,
  "rounds": [
    {
      "id": "round_1",
      "question": "Name something people do right after arriving at a party.",
      "answers": [
        { "id": "a1", "text": "Say hello", "points": 36, "aliases": ["greet"] },
        { "id": "a2", "text": "Look for food", "points": 25, "aliases": ["snacks"] },
        { "id": "a3", "text": "Find friends", "points": 18, "aliases": [] }
      ]
    }
  ]
}
```

Validation:

- `round_count`: 1-20, capped by available rounds.
- `max_strikes`: 1-5.
- `guess_time_seconds`: 10-180.
- Each round requires a question and at least 3 answers.
- Each answer requires text and points.
- Alias text is host-only metadata in MVP.

## Backend Events

Player to server:

```json
{ "type": "SURVEY_SUBMIT_GUESS", "guess": "Cake" }
```

Organizer to server:

```json
{ "type": "SURVEY_REVEAL_ANSWER", "answer_id": "a1" }
{ "type": "SURVEY_STRIKE" }
{ "type": "SURVEY_REVEAL_ALL" }
{ "type": "SURVEY_NEXT_ROUND" }
```

Server to clients:

```json
{
  "type": "SURVEY_SYNC",
  "game_type": "survey_says",
  "survey_says": {
    "phase": "SURVEY_ANSWERING",
    "round_number": 1,
    "total_rounds": 5,
    "question": "Name something people do right after arriving at a party.",
    "answers": [],
    "teams": [],
    "standings": []
  }
}
```

## Redaction

- Host sync includes answer text, aliases, and all submitted guesses.
- Player sync includes only revealed answer text and that player's own latest guess.
- Spectator sync includes revealed answer text and no private guesses.
- Podium/reveal phases may show all answer text.

## Follow-Ups

- AI/manual Survey Says pack authoring.
- Host-app/Revelry quick-start policy row and embedded QA.
- Optional buzzer/faceoff opening mechanic.
- Optional automatic answer matching suggestions for the host.
- Richer team names and manual team assignment.
