# prompts/

Versioned system prompts for all AlphaSoft AI surfaces. **Prompts are code**: every behavioral change is a new version file + a CHANGELOG entry, reviewed like any PR.

Rules:

- One file per prompt per version: `<surface>-system-v<N>.md`. Never edit a released version; create v(N+1).
- `{placeholders}` are runtime substitutions performed by the backend (see each file's header for the variable list).
- The backend (`Modules\Ai\Services\AiSystemPromptBuilder`) currently holds the copilot prompt inline as a PHP heredoc — `copilot-system-v1.md` mirrors it exactly. GAPS #10 tracks making the backend load released versions from here instead. Until then: any change here must be manually synced to the builder in the same PR, and vice versa.
- Prompt changes require an eval run (`evals/`) before release once the harness exists.
