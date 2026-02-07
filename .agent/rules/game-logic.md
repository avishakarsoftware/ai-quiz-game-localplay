---
trigger: always_on
---

# Development Rules for AI Quiz Game

- **Code Style:** Use Python for the backend and React/TypeScript for the PWA.
- **PWA Requirements:** The client must be mobile-first. Use Tailwind CSS for a "Kahoot" look (vibrant colors, large buttons).
- **Game Flow:** 1. Organizer gives prompt -> Agent calls `quiz-master` skill.
    2. Agent presents JSON to Organizer for approval.
    3. Once approved, Agent triggers `generate-image` for each question.
    4. Setup "Room View" with a QR code (use a library like `qrcode.react`).
- **Real-time:** Use WebSockets for the leaderboard and fastest-finger logic.