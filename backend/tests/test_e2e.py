"""
Full end-to-end integration test with live Ollama.
Tests: quiz generation -> editing -> room creation -> WebSocket game flow -> reconnection.
Also tests: export/import, custom num_questions, streak, teams, power-ups, spectator, game history.
Requires: Ollama running with qwen2.5:14b-instruct (or OLLAMA_MODEL env var).
"""
import sys
import os
import json
import time
import asyncio

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from main import app, quizzes, quiz_images, game_history
from socket_manager import socket_manager


@pytest.fixture(autouse=True)
def clear_state():
    quizzes.clear()
    quiz_images.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []
    yield
    quizzes.clear()
    quiz_images.clear()
    game_history.clear()
    socket_manager.rooms.clear()
    socket_manager.allowed_origins = saved_origins


client = TestClient(app)


def recv_until(ws, msg_type, max_messages=50):
    """Receive WS messages until we get the expected type."""
    for _ in range(max_messages):
        data = ws.receive_json()
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type} after {max_messages} messages")


class TestEndToEnd:
    """Full game flow: generate quiz -> edit -> create room -> play -> podium."""

    def test_full_game_flow(self):
        # ==========================================
        # Step 1: Generate quiz with Ollama (custom num_questions)
        # ==========================================
        print("\n--- Step 1: Generate quiz (difficulty=easy, num_questions=5) ---")
        res = client.post("/quiz/generate", json={
            "prompt": "5 questions about colors and shapes",
            "difficulty": "easy",
            "num_questions": 5,
        })
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        data = res.json()
        quiz_id = data["quiz_id"]
        quiz = data["quiz"]
        print(f"Quiz: '{quiz['quiz_title']}', {len(quiz['questions'])} questions")
        assert len(quiz["questions"]) >= 1
        for q in quiz["questions"]:
            assert len(q["options"]) in (2, 4), f"Q{q['id']} has {len(q['options'])} options"
            assert 0 <= q["answer_index"] < len(q["options"])

        # ==========================================
        # Step 2: Edit a question
        # ==========================================
        print("\n--- Step 2: Edit quiz (update first question) ---")
        original_text = quiz["questions"][0]["text"]
        quiz["questions"][0]["text"] = "EDITED: " + original_text
        res = client.put(f"/quiz/{quiz_id}", json=quiz)
        assert res.status_code == 200
        assert res.json()["quiz"]["questions"][0]["text"].startswith("EDITED:")

        # Delete a question if we have more than 3
        if len(quiz["questions"]) > 3:
            qid_to_delete = quiz["questions"][-1]["id"]
            res = client.delete(f"/quiz/{quiz_id}/question/{qid_to_delete}")
            assert res.status_code == 200
            quiz = res.json()["quiz"]
            print(f"Deleted question {qid_to_delete}, now {len(quiz['questions'])} questions")

        num_questions = len(quiz["questions"])

        # ==========================================
        # Step 2b: Export / Import roundtrip
        # ==========================================
        print("\n--- Step 2b: Export / Import quiz ---")
        res = client.get(f"/quiz/{quiz_id}/export")
        assert res.status_code == 200
        exported = res.json()["quiz"]
        assert exported["quiz_title"] == quiz["quiz_title"]

        res = client.post("/quiz/import", json={"quiz": exported})
        assert res.status_code == 200
        imported_id = res.json()["quiz_id"]
        assert imported_id != quiz_id
        assert res.json()["quiz"]["quiz_title"] == quiz["quiz_title"]
        print(f"Exported quiz {quiz_id}, imported as {imported_id}")

        # ==========================================
        # Step 3: Create room
        # ==========================================
        print("\n--- Step 3: Create room ---")
        res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": 8})
        assert res.status_code == 200
        room_data = res.json()
        room_code = room_data["room_code"]
        org_token = room_data["organizer_token"]
        print(f"Room: {room_code}")

        # ==========================================
        # Step 4: Connect organizer
        # ==========================================
        print("\n--- Step 4: Connect organizer ---")
        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true&token={org_token}") as org_ws:
            msg = org_ws.receive_json()
            assert msg["type"] == "ROOM_CREATED"

            # ==========================================
            # Step 5: Connect 3 players with teams
            # ==========================================
            print("\n--- Step 5: Connect players with teams ---")
            players = [
                {"name": "Alice", "team": "Red"},
                {"name": "Bob", "team": "Blue"},
                {"name": "Charlie", "team": "Red"},
            ]
            player_ws_list = []

            for i, p in enumerate(players):
                ws = client.websocket_connect(f"/ws/{room_code}/player-{i}")
                ws.__enter__()
                player_ws_list.append(ws)

                joined = ws.receive_json()
                assert joined["type"] == "JOINED_ROOM"

                ws.send_json({"type": "JOIN", "nickname": p["name"], "team": p["team"]})

                # Drain PLAYER_JOINED from organizer
                org_msg = recv_until(org_ws, "PLAYER_JOINED")
                assert org_msg["nickname"] == p["name"]
                assert "players" in org_msg
                assert p["name"] in org_msg["players"]
                print(f"  {p['name']} joined (team {p['team']}). Players: {org_msg['players']}")

                # Each player also gets PLAYER_JOINED
                for pw in player_ws_list:
                    player_msg = recv_until(pw, "PLAYER_JOINED")
                    assert p["name"] in player_msg["players"]

            # ==========================================
            # Step 6: Start game
            # ==========================================
            print("\n--- Step 6: Start game ---")
            org_ws.send_json({"type": "START_GAME"})
            org_ws.send_json({"type": "NEXT_QUESTION"})

            game_start = recv_until(org_ws, "QUESTION")
            assert game_start["question_number"] == 1
            assert "is_bonus" in game_start  # Bonus flag should always be present
            print(f"First question: {game_start['question']['text'][:60]}... (bonus={game_start['is_bonus']})")

            # Players receive GAME_STARTING and then QUESTION
            for pw in player_ws_list:
                recv_until(pw, "QUESTION")

            # ==========================================
            # Step 6b: Alice uses 50/50 power-up on Q1
            # ==========================================
            print("\n--- Step 6b: Alice uses 50/50 ---")
            player_ws_list[0].send_json({"type": "USE_POWER_UP", "power_up": "fifty_fifty"})
            pu_msg = recv_until(player_ws_list[0], "POWER_UP_ACTIVATED")
            assert pu_msg["power_up"] == "fifty_fifty"
            assert len(pu_msg["remove_indices"]) >= 1
            print(f"  50/50 removed indices: {pu_msg['remove_indices']}")

            # ==========================================
            # Step 7: Play through all questions
            # ==========================================
            alice_streak = 0
            bonus_flags = [game_start["is_bonus"]]  # Track bonus flags
            for q_num in range(1, num_questions + 1):
                print(f"\n--- Question {q_num}/{num_questions} ---")

                # Get correct answer from quiz data
                correct_answer = quiz["questions"][q_num - 1]["answer_index"]
                wrong_answer = (correct_answer + 1) % len(quiz["questions"][q_num - 1]["options"])

                if q_num > 1:
                    # Navigate to next question
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q_msg = recv_until(org_ws, "QUESTION")
                    assert "is_bonus" in q_msg
                    bonus_flags.append(q_msg["is_bonus"])
                    for pw in player_ws_list:
                        recv_until(pw, "QUESTION")

                # Bob uses double_points on Q2
                if q_num == 2:
                    print("  Bob activates double_points!")
                    player_ws_list[1].send_json({"type": "USE_POWER_UP", "power_up": "double_points"})
                    pu2 = recv_until(player_ws_list[1], "POWER_UP_ACTIVATED")
                    assert pu2["power_up"] == "double_points"

                # Each player answers
                for i, pw in enumerate(player_ws_list):
                    # Alice always answers correctly using quiz data
                    # Bob answers correctly on Q2 (to test double points)
                    # Others answer wrong
                    if i == 0:
                        answer = correct_answer
                    elif i == 1 and q_num == 2:
                        answer = correct_answer
                    else:
                        answer = wrong_answer
                    pw.send_json({"type": "ANSWER", "answer_index": answer})
                    result = recv_until(pw, "ANSWER_RESULT")
                    assert "is_bonus" in result  # Bonus flag in answer result
                    status = "correct" if result["correct"] else "wrong"
                    bonus_info = " BONUS!" if result["is_bonus"] else ""
                    streak_info = f" streak={result.get('streak', 0)} mult={result.get('multiplier', 1.0)}"
                    print(f"  {players[i]['name']}: answer={answer}, {status}, +{result['points']}pts{streak_info}{bonus_info}")

                    # Verify Alice's streak increments
                    if i == 0:
                        alice_streak += 1
                        assert result["correct"] is True
                        assert result["streak"] == alice_streak
                        if alice_streak >= 3:
                            assert result["multiplier"] == 1.5

                    # Verify Bob's double points on Q2
                    if i == 1 and q_num == 2:
                        assert result["correct"] is True
                        print(f"  Bob got {result['points']}pts with double_points")

                # Wait for QUESTION_OVER
                qo = recv_until(org_ws, "QUESTION_OVER")
                assert "leaderboard" in qo
                print(f"  Leaderboard: {[(e['nickname'], e['score']) for e in qo['leaderboard']]}")

                for pw in player_ws_list:
                    recv_until(pw, "QUESTION_OVER")

            # Verify bonus flags
            print(f"\nBonus flags: {bonus_flags}")
            assert bonus_flags[0] is False, "First question should not be bonus"
            assert bonus_flags[-1] is False, "Last question should not be bonus"
            if num_questions >= 4:
                assert True in bonus_flags, "Should have at least one bonus question"

            # ==========================================
            # Step 8: Show podium
            # ==========================================
            print("\n--- Step 8: Podium ---")
            org_ws.send_json({"type": "NEXT_QUESTION"})
            podium = recv_until(org_ws, "PODIUM")
            assert "leaderboard" in podium
            assert "team_leaderboard" in podium
            print("Final standings:")
            for i, entry in enumerate(podium["leaderboard"]):
                print(f"  #{i+1} {entry['nickname']}: {entry['score']}pts")

            # Alice should be first (always correct)
            assert podium["leaderboard"][0]["nickname"] == "Alice"

            # Team leaderboard should have Red and Blue
            tl = podium["team_leaderboard"]
            assert len(tl) == 2
            team_names = {t["team"] for t in tl}
            assert team_names == {"Red", "Blue"}
            print("Team standings:")
            for t in tl:
                print(f"  {t['team']}: {t['score']}pts ({t['members']} members)")

            # Red team should be first (Alice always correct + Charlie)
            assert tl[0]["team"] == "Red"

            for pw in player_ws_list:
                p_podium = recv_until(pw, "PODIUM")
                assert "leaderboard" in p_podium
                assert "team_leaderboard" in p_podium

            # ==========================================
            # Step 9: Verify game history
            # ==========================================
            print("\n--- Step 9: Verify game history ---")
            res = client.get("/history")
            assert res.status_code == 200
            games = res.json()["games"]
            assert len(games) == 1
            assert games[0]["room_code"] == room_code
            print(f"Game history: {games[0]['quiz_title']}, {games[0]['player_count']} players")

            res = client.get(f"/history/{room_code}")
            assert res.status_code == 200
            detail = res.json()
            assert detail["player_count"] == 3
            assert len(detail["answer_log"]) == num_questions * 3  # 3 players * questions
            assert len(detail["team_leaderboard"]) == 2
            print(f"Answer log: {len(detail['answer_log'])} entries")

            # ==========================================
            # Cleanup
            # ==========================================
            for pw in player_ws_list:
                pw.__exit__(None, None, None)

        print("\n--- E2E test passed! ---")


class TestReconnectionE2E:
    """Test player reconnection during an active game."""

    def test_player_reconnects_with_score(self):
        # Seed a simple 3-question quiz directly
        quiz_data = {
            "quiz_title": "Reconnect Test",
            "questions": [
                {"id": i+1, "text": f"Q{i+1}?", "options": ["A", "B", "C", "D"], "answer_index": 0}
                for i in range(3)
            ],
        }
        import uuid
        quiz_id = str(uuid.uuid4())
        quizzes[quiz_id] = quiz_data

        res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": 30})
        room_data = res.json()
        room_code = room_data["room_code"]
        org_token = room_data["organizer_token"]

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true&token={org_token}") as org_ws:
            org_ws.receive_json()  # ROOM_CREATED

            # Player joins
            with client.websocket_connect(f"/ws/{room_code}/player-1") as p_ws:
                p_ws.receive_json()  # JOINED_ROOM
                p_ws.send_json({"type": "JOIN", "nickname": "Alice"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                # Start game, first question
                org_ws.send_json({"type": "START_GAME"})
                org_ws.send_json({"type": "NEXT_QUESTION"})
                recv_until(org_ws, "QUESTION")
                recv_until(p_ws, "QUESTION")

                # Answer correctly
                p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                result = recv_until(p_ws, "ANSWER_RESULT")
                assert result["correct"] is True
                score_before = result["points"]
                assert result["streak"] == 1
                print(f"Alice scored {score_before} points before disconnect")

            # Player disconnected! WebSocket closed.
            # Wait a moment for the server to process the disconnect
            time.sleep(0.5)

            # Verify player data is preserved
            room = socket_manager.rooms[room_code]
            assert "Alice" in room.disconnected_players
            assert room.disconnected_players["Alice"]["score"] == score_before
            assert room.disconnected_players["Alice"]["streak"] == 1

            # Player reconnects
            with client.websocket_connect(f"/ws/{room_code}/player-2") as p_ws2:
                p_ws2.receive_json()  # JOINED_ROOM
                p_ws2.send_json({"type": "JOIN", "nickname": "Alice"})

                # Should get RECONNECTED instead of PLAYER_JOINED
                recon = recv_until(p_ws2, "RECONNECTED")
                assert recon["score"] == score_before
                print(f"Alice reconnected with score {recon['score']}")
                assert "Alice" not in room.disconnected_players

        print("--- Reconnection E2E test passed! ---")


class TestExportImportE2E:
    """E2E test for export/import with live Ollama-generated quiz."""

    def test_generate_export_import_play(self):
        """Generate a quiz, export it, import it, and play a game with the imported copy."""
        # Step 1: Generate quiz
        print("\n--- Generate quiz for export/import ---")
        res = client.post("/quiz/generate", json={
            "prompt": "3 questions about animals",
            "difficulty": "medium",
            "num_questions": 3,
        })
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        original_id = res.json()["quiz_id"]
        original_quiz = res.json()["quiz"]
        print(f"Generated: '{original_quiz['quiz_title']}', {len(original_quiz['questions'])} questions")

        # Step 2: Export
        res = client.get(f"/quiz/{original_id}/export")
        assert res.status_code == 200
        exported = res.json()["quiz"]

        # Step 3: Import
        res = client.post("/quiz/import", json={"quiz": exported})
        assert res.status_code == 200
        imported_id = res.json()["quiz_id"]
        assert imported_id != original_id
        print(f"Exported {original_id} -> imported as {imported_id}")

        # Step 4: Create room with imported quiz and play
        res = client.post("/room/create", json={"quiz_id": imported_id, "time_limit": 10})
        assert res.status_code == 200
        room_data = res.json()
        room_code = room_data["room_code"]
        org_token = room_data["organizer_token"]

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true&token={org_token}") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "Tester"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                # Play through all questions
                for _ in range(len(original_quiz["questions"])):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(p_ws, "QUESTION")
                    recv_until(org_ws, "QUESTION")
                    # Answer with index 0
                    p_ws.send_json({"type": "ANSWER", "answer_index": 0})
                    recv_until(p_ws, "ANSWER_RESULT")
                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert podium["leaderboard"][0]["nickname"] == "Tester"

        print("--- Export/Import E2E test passed! ---")


class TestBonusRoundsE2E:
    """E2E test for bonus rounds with live Ollama-generated quiz."""

    def test_bonus_rounds_with_live_quiz(self):
        """Generate a 6-question quiz, play through, verify bonus round behavior."""
        # Step 1: Generate quiz with enough questions for bonus selection
        print("\n--- Generate 6-question quiz for bonus test ---")
        res = client.post("/quiz/generate", json={
            "prompt": "6 questions about geography and world capitals",
            "difficulty": "easy",
            "num_questions": 6,
        })
        assert res.status_code == 200, f"Quiz generation failed: {res.text}"
        quiz_id = res.json()["quiz_id"]
        quiz = res.json()["quiz"]
        num_questions = len(quiz["questions"])
        print(f"Generated: '{quiz['quiz_title']}', {num_questions} questions")
        assert num_questions >= 4, "Need at least 4 questions for bonus rounds"

        # Step 2: Create room and connect
        res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": 10})
        assert res.status_code == 200
        room_data = res.json()
        room_code = room_data["room_code"]
        org_token = room_data["organizer_token"]

        with client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true&token={org_token}") as org_ws:
            org_ws.receive_json()

            with client.websocket_connect(f"/ws/{room_code}/p-1") as p_ws:
                p_ws.receive_json()
                p_ws.send_json({"type": "JOIN", "nickname": "BonusTester"})
                recv_until(org_ws, "PLAYER_JOINED")
                recv_until(p_ws, "PLAYER_JOINED")

                org_ws.send_json({"type": "START_GAME"})

                bonus_flags = []
                bonus_points = []
                normal_points = []

                for q_num in range(num_questions):
                    org_ws.send_json({"type": "NEXT_QUESTION"})
                    q = recv_until(org_ws, "QUESTION")
                    recv_until(p_ws, "QUESTION")

                    assert "is_bonus" in q
                    bonus_flags.append(q["is_bonus"])
                    print(f"  Q{q_num+1}: bonus={q['is_bonus']}")

                    # Answer with the correct answer from quiz data
                    correct = quiz["questions"][q_num]["answer_index"]
                    p_ws.send_json({"type": "ANSWER", "answer_index": correct})
                    result = recv_until(p_ws, "ANSWER_RESULT")
                    assert "is_bonus" in result
                    assert result["is_bonus"] == q["is_bonus"]

                    if result["correct"]:
                        if q["is_bonus"]:
                            bonus_points.append(result["points"])
                        else:
                            normal_points.append(result["points"])
                        print(f"    +{result['points']}pts (streak={result['streak']}, mult={result['multiplier']})")

                    recv_until(org_ws, "QUESTION_OVER")
                    recv_until(p_ws, "QUESTION_OVER")

                # Verify bonus round constraints
                print(f"\nBonus flags: {bonus_flags}")
                assert bonus_flags[0] is False, "First question must not be bonus"
                assert bonus_flags[-1] is False, "Last question must not be bonus"
                assert True in bonus_flags, "Should have at least one bonus question"
                assert False in bonus_flags, "Should have at least one non-bonus question"

                # Podium
                org_ws.send_json({"type": "NEXT_QUESTION"})
                podium = recv_until(org_ws, "PODIUM")
                assert podium["leaderboard"][0]["nickname"] == "BonusTester"

                # Verify team_leaderboard has solo player entry
                tl = podium["team_leaderboard"]
                assert len(tl) == 1
                assert tl[0]["team"] == "BonusTester"
                assert tl[0]["members"] == 1

        print("--- Bonus Rounds E2E test passed! ---")
