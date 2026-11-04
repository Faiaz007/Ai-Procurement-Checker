# BIAI AI Engineer: Round 2 Task

Congratulations on reaching Round 2. In this round we want to see how you build.

## The rules

- **Choose ONE of the two tasks below.**
- **You have 72 hours** from when you get this brief.
- **Use any AI tools you like** (Claude, ChatGPT, Cursor, Copilot and so on). We want to see how you use them.
- **Use only the sample files we send you.** Do not use real company or customer data.
- If you need more time because of exams or work, you can ask once for 24 extra hours, before the deadline.

## What to send us

1. **A Loom video (5 minutes or less) where you present your solution.** This is a core part of the task, not an extra. Explain the problem, show it working on our sample files, and tell us why you made your choices and what you would improve. We are hiring people who can explain and sell what they build to non-technical people, so we score this video.
2. **A working link** to your demo, if you have one.
3. **Your code:** a GitHub link, with a README that explains how to run it.
4. **A one-page note:** what you built, how you tested it, your results, what does not work well, and what you would do next.

If we shortlist you, we will have a 30-minute call where you show us your work and we ask you to change one thing live.

---

## Task 1: Check supplier documents

**The idea.** A garment company gets quotes and contracts from suppliers. Build an AI system that checks them step by step and never guesses.

**Your system should:**

1. Read each supplier quote and pull out the supplier name, items, quantities, prices and delivery date.
2. Compare the quote with the company's purchase request and point out any wrong quantity or price.
3. Check the contract against a short list of company rules (for example payment terms and VAT).
4. Give a final answer for each document: **Approve**, **Reject** or **Needs a person to check**, with the reason.
5. When it is not sure, stop and ask a person. Do not guess.

**Important:** build it as clear fixed steps, one after another (for example with LangGraph, LlamaIndex Workflows or n8n). Do not build one agent that runs freely on its own.

**We send you:** 10 sample quotes and contracts (some correct, some with mistakes), the purchase request and the rule list.

**Show us:** how many of the 10 your system got right.

---

## Task 2: A bilingual assistant that runs offline

**The idea.** A bank wants a chat assistant for its customers. Customers write in English, Bangla or Banglish (Bangla in English letters). The bank does not allow customer data to go to outside AI services, so the assistant must run on a small AI model on their own computer.

**Your assistant should:**

1. Answer questions using only the bank FAQ we give you.
2. Reply in the same language the customer used: English, Bangla or Banglish.
3. Run on a small open model (for example Qwen, Llama, Gemma or Phi) on your own computer, or on a free Colab or Kaggle GPU.
4. Say "I don't know, let me connect you to a person" if the answer is not in the FAQ.

**We send you:** the bank FAQ and 40 test questions in mixed languages. Some questions are not covered by the FAQ on purpose.

**Show us:** your results on the 40 questions (how many were right, how often it correctly said "I don't know", and how fast it answered). Then run the same 40 questions on any online AI model and compare.

**Extra (optional):** train the small model further on banking words or Banglish, and show if it got better.

---

## How we score (the same for both tasks)

| What we check | Weight |
|---|---|
| Your Loom presentation: clear, confident, explains the why, a non-technical person could follow it | 20% |
| It works correctly on our sample files | 25% |
| It is built in a clear, sensible way and handles mistakes | 20% |
| How well you solved the hardest part of your task | 15% |
| Clean code that we can run from your README | 10% |
| Honesty: your note says clearly what does not work | 10% |

Good luck. We look forward to seeing what you build.

BIAI Hiring Team, support@biai.com.bd
