# Security

Everything runs locally against Ollama at `127.0.0.1:11434`; nothing else is contacted. Two things to
know before you expose it: every question asked, accepted or refused, is appended in full to `audit.jsonl`
on the host, so treat that file as you would a log of user input; and the corpus is read from `corpus/*.md`
without sandboxing, so anyone who can write there decides what the model is allowed to cite.

To report a security problem, write to office@devaland.com with the commit, the command and a way to
reproduce it. Please do not open a public issue for it. A person answers; there is no bug bounty.
