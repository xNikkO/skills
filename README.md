# Skille dla agentów AI

Skille dla agentów AI, przeznaczone do używania między projektami i przez różnych użytkowników.

## Instalacja przez skills CLI

Wymagania: T3 Code z dostępnymi narzędziami delegacji, Python 3 oraz odpowiedni provider i model recenzenta. Instalacja skilla nie instaluje T3 Code ani nie konfiguruje providerów.

Oba skille można zainstalować globalnie dla Codexa i Claude Code:

```bash
npx skills add xNikkO/skills --skill t3-review-loop t3-review-loop-local --agent codex claude-code --global
```

Instalacja pojedynczego skilla:

```bash
npx skills add xNikkO/skills --skill t3-review-loop
npx skills add xNikkO/skills --skill t3-review-loop-local
```

Lista dostępnych skilli bez instalowania:

```bash
npx skills add xNikkO/skills --list
```

## T3 review loop

[Instrukcje skilla](skills/t3-review-loop/SKILL.md) prowadzą niezależne review bezpieczeństwa i poprawności kodu przez T3 Code. Agent prowadzący naprawia potwierdzone błędy, uruchamia odpowiednie testy i ponawia review aż każdy PR oraz cała zmiana otrzymają **Safe To Merge co najmniej 9/10**.

| Agent prowadzący i implementujący | Reviewer |
| --- | --- |
| Codex | Claude Opus 5.5 |
| Claude | GPT-6.1-Sol |

Ocena dotyczy aktualnych commitów. Rzeczywiste blokady i brak wymaganej weryfikacji są zgłaszane, zamiast sztucznie podnosić ocenę. Skill wymaga narzędzi delegacji T3 Code i dostępności wskazanych modeli.

W obu wariantach **Safe To Merge i status CI są raportowane osobno**. Brak zakończonego CI nie obniża oceny i nie czyni jej warunkową: poprawny kod może otrzymać **9/10, CI: pending**. Samo przejście CI nie wymaga kolejnego review. Potwierdzony błąd kodu wykryty przez CI nadal wymaga naprawy; wymagane checks muszą przejść przed faktycznym mergowaniem.

Każda runda zostawia komentarz na PR z konta, które go opublikowało; agent sprawdza autora PR i zalogowane konto osobno dla każdego PR. Brak dostępu do odpowiedniego konta jest zgłaszany jako blokada publikowania. Skill nie zawiera przypisanej na stałe tożsamości użytkownika i **nie merguje PR-ów**.

Po zakończeniu agent podaje liczbę ukończonych review, historię ocen dla każdego PR i całej zmiany, znalezione błędy, naprawy między rundami i wyniki weryfikacji. Podsumowanie kończy opisem tego, co zaimplementowano w zadaniu i co naprawiono podczas review. PR-y pozostają otwarte.

### Użycie

```text
$t3-review-loop Sprawdź i popraw PR <link>.
```

### Instalacja globalna

Sklonuj repozytorium do wybranego katalogu. Folder `skills/t3-review-loop` udostępnij jako skill globalny w `~/.agents/skills/`. Możesz również utworzyć do niego dowiązania w katalogach skilli Claude’a (`~/.claude/skills/`) i Codexa (`$CODEX_HOME/skills/`, domyślnie `~/.codex/skills/`). Zachowaj nazwę `t3-review-loop` i istniejące skille w tych katalogach.

W T3 Code nowe skille mogą wymagać odświeżenia listy lub rozpoczęcia nowego wątku.

## T3 review loop local

[Wariant lokalny](skills/t3-review-loop-local/SKILL.md) prowadzi implementację, review i naprawy w rozmowie agentów T3 Code. Kod pozostaje lokalnie — również bez draft PR i bez pushowania — aż każda część zmiany oraz całość uzyskają **Safe To Merge co najmniej 9/10** i przejdą odpowiednią weryfikację lokalną. Dopiero wtedy agent pushuje dokładnie sprawdzony kod i wystawia PR.

Opis PR zawiera liczbę ukończonych review przed publikacją, historię ocen, znalezione findingi, ich naprawy lub obalenia, identyfikatory sprawdzonego kodu i wyniki testów. Brak remote CI przed utworzeniem PR sam w sobie nie blokuje lokalnego review; po publikacji wymagane CI nadal musi przejść przed mergowaniem. Skill nie merguje PR-ów.

Gdy oba providery są dostępne, obowiązuje Codex → Claude Opus 5.5 oraz Claude → GPT-6.1-Sol. **Wyłącznie gdy druga rodzina jest niedostępna**, review robi osobny agent z dostępnej rodziny: GPT → GPT lub Claude → Claude. Sam brak konkretnego modelu lub błąd uruchomienia nie włącza takiego fallbacku.

```text
$t3-review-loop-local Zaimplementuj <zadanie>, zrób lokalny review i wystaw PR dopiero po pozytywnym wyniku.
```

Instalacja jak wyżej, z folderem i nazwą `t3-review-loop-local`. Oba skille mogą być zainstalowane równocześnie; dotychczasowy `t3-review-loop` pozostaje wersją dla review opublikowanych PR-ów.

## Struktura

```text
skills/t3-review-loop/
├── SKILL.md
├── agents/openai.yaml
├── references/reviewer-prompt.md
└── scripts/select_reviewer.py
```

Helper wybiera reviewera z aktualnego katalogu T3 Code, pomija nieaktywne providery i nie zastępuje po cichu wskazanego modelu innym.

Wariant `skills/t3-review-loop-local/` ma osobny helper routingu i dodatkowy szablon `references/pr-description.md`, opisujący historię lokalnego review w późniejszym PR.
