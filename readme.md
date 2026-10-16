+-----------------------------------------------------------------------------------+
|                        STREAMLIT UI & SESSION LAYER                               |
|  - Teacher Dashboard (Config, Syllabus Mapping, Autonomous Scheduling)             |
|  - Student Exam Portal (Authentication, Anti-Cheating Set Retrieval, Submission)   |
|  - Analytics, Diagnostic Reports Hub & Live SQLite Inspector                      |
+-----------------------------------------------------------------------------------+
         |                                                           |
         | (Saves Pending Config)                                    | (Pulls Reports & Grades)
         v                                                           v
+-----------------------------------------------------------------------------------+
|                            SQLITE PERSISTENCE LAYER                               |
|  - paper_configs | paper_sets | students | student_assignments | submissions  |
|  - student_reports | agent_scheduler_logs                                         |
+-----------------------------------------------------------------------------------+
         ^
         | (Polls every 10s for Pending configs <= Now)
+-----------------------------------------------------------------------------------+
|                  BACKGROUND CRON WORKER THREAD (daemon=True)                      |
|  - Retrieves Global API Key securely via st.secrets                               |
|  - Invokes LangGraph Pipeline                                                     |
+-----------------------------------------------------------------------------------+
         |
         v
+-----------------------------------------------------------------------------------+
|                      LANGGRAPH MULTI-AGENT PIPELINE                               |
|  1. Syllabus Validator Agent  -->  2. Question Generator Agent (Groq / Llama3)    |
|  3. QA & Red-Teaming Auditor  -->  4. Persistence & Student Assignment Agent      |
+-----------------------------------------------------------------------------------+