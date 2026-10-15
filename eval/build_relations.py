#!/usr/bin/env python3
"""build_relations.py - builds items_relations.jsonl: the "relations" set (who must do what, by when).

WHY. The first set (items.jsonl) tests ABSTENTION: does a model stop when the text does not hold the answer.
It cannot see a different failure: an answer built from words that ARE in the text but attached to the wrong
party or the wrong action. Example that started this set: Legea 544/2001 art. 21 (3), the 15 days are the
authority's deadline to answer a justified complaint; a model answered them as the applicant's deadline to
complain. Every word of that answer is in the text, so a provenance check passes it.

HOW. Each GROUP is built on ONE source span (copied verbatim from sources/, checked below) and has exactly
three variants, adjacent in the file, sharing group id and span. Only the relation under test changes:
  valid        a low-lexical-overlap paraphrase with the correct actor, action and deadline/obligation.
               A gate SHOULD ACCEPT it.            (expected: accept)
  wrong_actor  the same number/obligation, assigned to the OTHER party. A gate SHOULD REJECT it.   (expected: reject)
  wrong_action the RIGHT actor and the right number, but the obligation attached to a DIFFERENT action.
               A gate SHOULD REJECT it.            (expected: reject)
Two rates are reported, each over its OWN denominator (run_relations.py):
  1. wrong answers ACCEPTED / all wrong variants (wrong_actor, wrong_action, and combined)
  2. valid paraphrases REFUSED / all valid variants   (a gate that refuses everything scores 100% here)

The spans are ORIGINAL texts (legislatie.just.ro) already in sources/. The test measures grounding in the text it
is given, not legal truth. The wrong answers are written by us as test material; they are NOT legal statements.
Some wrong_action answers describe an action that exists elsewhere in the same law (e.g. a court complaint);
they are wrong ONLY against the given span, which is exactly the relation tested.
"""
import json, os, re, sys

S544, S190, S600 = "sources/legea-544-2001.txt", "sources/legea-190-2018.txt", "sources/ordin-sgg-600-2018.txt"

# (group, source file, source label, span, question, valid, wrong_actor, wrong_action)
G = [
 ("refuz-5-zile", S544, "Legea 544/2001 art. 7 alin. (2)",
  "Refuzul comunicării informaţiilor solicitate se motiveaza şi se comunică în termen de 5 zile de la primirea petitiilor.",
  "Cine trebuie să motiveze și să comunice refuzul de a da informațiile solicitate, și în ce termen?",
  "Autoritatea care nu oferă informațiile are 5 zile de la primirea cererii ca să explice refuzul și să-l aducă la cunoștința petentului.",
  "Persoana care a cerut informațiile are 5 zile de la primirea petiției ca să motiveze și să comunice contestarea refuzului.",
  "Autoritatea are 5 zile de la primirea petiției ca să furnizeze informațiile solicitate."),
 ("raspuns-10-30-zile", S544, "Legea 544/2001 art. 7 alin. (1), prima teză",
  "Autorităţile şi instituţiile publice au obligaţia sa răspundă în scris la solicitarea informaţiilor de interes public în termen de 10 zile sau, după caz, în cel mult 30 de zile de la înregistrarea solicitării, în funcţie de dificultatea, complexitatea, volumul lucrărilor documentare şi de urgenta solicitării.",
  "Cine trebuie să răspundă în scris la o solicitare de informații de interes public, și în ce termen?",
  "Instituția căreia i s-a cerut informația trebuie să dea un răspuns scris în 10 zile de la înregistrarea cererii, iar când lucrarea e mai grea sau mai voluminoasă, în cel mult 30.",
  "Cel care cere informația de interes public trebuie să depună în scris solicitarea în 10 zile sau, după caz, în cel mult 30 de zile de la înregistrarea ei.",
  "Autoritățile și instituțiile publice au obligația să motiveze refuzul în 10 zile sau, după caz, în cel mult 30 de zile de la înregistrarea solicitării."),
 ("presa-verbal-24-ore", S544, "Legea 544/2001 art. 8 alin. (5)",
  "Informaţiile de interes public solicitate verbal de către mijloacele de informare în masa vor fi comunicate, de regula, imediat sau în cel mult 24 de ore.",
  "Cine comunică informațiile de interes public cerute verbal de presă, și în cât timp?",
  "Când ziariștii cer oral informații de interes public, instituția le dă, de obicei, pe loc ori cel târziu în 24 de ore.",
  "Mijloacele de informare în masă comunică instituției, de regulă imediat sau în cel mult 24 de ore, informațiile de interes public cerute verbal.",
  "Autoritatea acreditează, de regulă imediat sau în cel mult 24 de ore, mijloacele de informare în masă care au cerut verbal informații de interes public."),
 ("acreditare-2-zile", S544, "Legea 544/2001 art. 18 alin. (1)-(2)",
  "Autorităţile publice au obligaţia sa acorde fără discriminare acreditare ziaristilor şi reprezentanţilor mijloacelor de informare în masa. (2) Acreditarea se acordă la cerere, în termen de doua zile de la înregistrarea acesteia.",
  "Cine acordă acreditarea ziariștilor la cerere, și în ce termen?",
  "Autoritățile publice dau acreditarea ziariștilor, fără deosebiri între ei, în două zile de la momentul în care cererea a fost înregistrată.",
  "Ziaristul trebuie să ceară acreditarea în termen de două zile de la înregistrarea lui la autoritățile publice.",
  "Autoritățile publice retrag acreditarea ziariștilor, fără discriminare, în termen de două zile de la înregistrarea cererii."),
 ("reclamatie-30-zile", S544, "Legea 544/2001 art. 21 alin. (1)-(2)",
  "Refuzul explicit sau tacit al angajatului desemnat al unei autorităţi ori instituţii publice pentru aplicarea prevederilor prezentei legi constituie abatere şi atrage răspunderea disciplinară a celui vinovat. (2) Împotriva refuzului prevăzut la alin. (1) se poate depune reclamaţie la conducătorul autorităţii sau al instituţiei publice respective în termen de 30 de zile de la luarea la cunoştinţa de către persoana lezata.",
  "Cine poate depune reclamație împotriva refuzului angajatului desemnat, și în ce termen?",
  "Persoana nemulțumită de refuz se poate plânge șefului instituției în 30 de zile din momentul în care a aflat de refuz.",
  "Angajatul desemnat poate depune reclamație la conducătorul instituției în termen de 30 de zile de la luarea la cunoștință a refuzului.",
  "Persoana lezată are 30 de zile de la luarea la cunoștință a refuzului ca să solicite din nou informațiile angajatului desemnat."),
 ("reclamatie-15-zile", S544, "Legea 544/2001 art. 21 alin. (2)-(3) (cazul de la care a pornit setul)",
  "(2) Împotriva refuzului prevăzut la alin. (1) se poate depune reclamaţie la conducătorul autorităţii sau al instituţiei publice respective în termen de 30 de zile de la luarea la cunoştinţa de către persoana lezata. (3) Dacă după cercetarea administrativă reclamaţia se dovedeşte intemeiata, răspunsul se transmite persoanei lezate în termen de 15 zile de la depunerea reclamaţiei şi va conţine atât informaţiile de interes public solicitate iniţial, cat şi menţionarea sancţiunilor disciplinare luate împotriva celui vinovat.",
  "Cui revine termenul de 15 zile din text, și ce trebuie făcut în el?",
  "Dacă reclamația a fost găsită întemeiată, conducerea instituției trebuie să-i trimită celui lezat, în 15 zile de la depunere, informațiile cerute la început și sancțiunile aplicate vinovatului.",
  "Persoana lezată trebuie să depună reclamația la conducătorul instituției în termen de 15 zile.",
  "Conducătorul instituției are 15 zile de la depunerea reclamației ca să respingă reclamația persoanei lezate."),
 ("plangere-30-zile", S544, "Legea 544/2001 art. 22 alin. (1)",
  "În cazul în care o persoană se considera vătămată în drepturile sale, prevăzute în prezenta lege, aceasta poate face plângere la secţia de contencios administrativ a tribunalului în a carei raza teritorială domiciliază sau în a carei raza teritorială se afla sediul autorităţii ori al instituţiei publice. Plîngerea se face în termen de 30 de zile de la data expirării termenului prevăzut la art. 7.",
  "Cine poate face plângere la tribunal, și în ce termen?",
  "Cine se simte lezat în drepturile din această lege se adresează secției de contencios administrativ a tribunalului, în 30 de zile de la expirarea termenului prevăzut la art. 7.",
  "Autoritatea sau instituția publică face plângere la secția de contencios administrativ a tribunalului în termen de 30 de zile de la data expirării termenului prevăzut la art. 7.",
  "Persoana lezată face recurs împotriva hotărârii tribunalului în termen de 30 de zile de la data expirării termenului prevăzut la art. 7."),
 ("conferinte-lunar", S544, "Legea 544/2001 art. 17 alin. (1)",
  "Autorităţile publice au obligaţia sa organizeze periodic, de regula o dată pe luna, conferinţe de presa pentru aducerea la cunoştinţa a informaţiilor de interes public.",
  "Cine organizează conferințe de presă pentru informațiile de interes public, și cât de des?",
  "Instituțiile statului sunt obligate ca, în mod obișnuit, în fiecare lună să țină întâlniri cu presa în care să facă cunoscute informații de interes public.",
  "Mijloacele de informare în masă organizează periodic, de regulă o dată pe lună, conferințe de presă pentru aducerea la cunoștință a informațiilor de interes public.",
  "Autoritățile publice acreditează ziariștii periodic, de regulă o dată pe lună, pentru aducerea la cunoștință a informațiilor de interes public."),
 ("copii-cost", S544, "Legea 544/2001 art. 9 alin. (1)",
  "În cazul în care solicitarea de informaţii implica realizarea de copii de pe documentele deţinute de autoritatea sau instituţia publică, costul serviciilor de copiere este suportat de solicitant, în condiţiile legii.",
  "Cine suportă costul serviciilor de copiere a documentelor?",
  "Dacă cererea presupune fotocopii ale documentelor aflate la instituție, plata copierii cade în sarcina celui care a cerut informațiile.",
  "Costul serviciilor de copiere este suportat de autoritatea sau instituția publică care deține documentele.",
  "Costul serviciilor de traducere a documentelor deținute de autoritate este suportat de solicitant."),
 ("gdpr-reluare-control-10-zile", S190, "Legea 190/2018 art. 13 alin. (3)",
  "În termen de 10 zile de la data expirării termenului de remediere, Autoritatea națională de supraveghere poate să reia controlul.",
  "Cine poate relua controlul, și în ce termen?",
  "Autoritatea de supraveghere poate să verifice din nou în cel mult 10 zile de la expirarea perioadei acordate pentru remediere.",
  "Autoritatea sau organismul public poate să reia controlul în termen de 10 zile de la data expirării termenului de remediere.",
  "Autoritatea națională de supraveghere poate să aplice amenda în termen de 10 zile de la data expirării termenului de remediere."),
 ("gdpr-proces-verbal-avertisment", S190, "Legea 190/2018 art. 13 alin. (1)",
  "În cazul constatării încălcării prevederilor Regulamentului general privind protecția datelor și ale prezentei legi de către autoritățile/organismele publice, Autoritatea națională de supraveghere încheie un proces-verbal de constatare și sancționare a contravenției prin care se aplică sancțiunea avertismentului și la care anexează un plan de remediere.",
  "Cine încheie procesul-verbal când o autoritate publică încalcă regulile privind datele personale, și ce sancțiune se aplică?",
  "Dacă o instituție publică încalcă regulile privind datele personale, autoritatea de control consemnează fapta într-un act, o avertizează și atașează un plan de remediere.",
  "Autoritatea sau organismul public încheie procesul-verbal de constatare și aplică avertismentul Autorității naționale de supraveghere, anexând un plan de remediere.",
  "Autoritatea națională de supraveghere încheie procesul-verbal prin care aplică sancțiunea amenzii contravenționale și anexează un plan de remediere."),
 ("scim-raport-20-februarie", S600, "OSGG 600/2018 art. 9 alin. (2)",
  "(2) Instituțiile publice în care se exercită funcția de ordonator principal de credite al bugetului de stat, al bugetului asigurărilor sociale de stat sau al bugetului oricărui fond special transmit anual la DCIMRI, din cadrul Secretariatului General al Guvernului, Raportul asupra sistemului de control intern managerial la data de 31 decembrie prevăzut la alin. (1) , până la 20 februarie a anului următor, pentru anul precedent.",
  "Cine transmite la DCIMRI Raportul asupra sistemului de control intern managerial, și până când?",
  "Instituțiile care sunt ordonator principal de credite al bugetului de stat, al bugetului asigurărilor sociale de stat sau al unui fond special trimit în fiecare an către DCIMRI raportul privind situația la 31 decembrie, cel târziu pe 20 februarie din anul care urmează.",
  "DCIMRI transmite anual instituțiilor publice Raportul asupra sistemului de control intern managerial la data de 31 decembrie, până la 20 februarie a anului următor.",
  "Instituțiile publice ordonatoare principale de credite aprobă anual, până la 20 februarie a anului următor, Raportul asupra sistemului de control intern managerial la data de 31 decembrie."),
 ("scim-raport-elaborare", S600, "OSGG 600/2018 art. 9 alin. (1), începutul",
  "Conducătorul fiecărei entități publice elaborează anual Raportul asupra sistemului de control intern managerial la data de 31 decembrie în baza art. 4 alin. (3) din Ordonanța Guvernului nr. 119/1999 privind controlul intern managerial și controlul financiar preventiv, republicată, cu modificările și completările ulterioare, conform modelului prevăzut în Instrucțiunile privind întocmirea, aprobarea și prezentarea raportului asupra sistemului de control intern managerial, care se prezintă structurii ierarhic superioare",
  "Cine elaborează anual raportul asupra sistemului de control intern managerial, și cui se prezintă?",
  "În fiecare an, șeful entității publice întocmește raportul privind situația controlului intern managerial la 31 decembrie și îl înaintează structurii situate deasupra lui în ierarhie.",
  "Structura ierarhic superioară elaborează anual Raportul asupra sistemului de control intern managerial la data de 31 decembrie, care se prezintă conducătorului fiecărei entități publice.",
  "Conducătorul fiecărei entități publice aprobă anual Raportul asupra sistemului de control intern managerial la data de 31 decembrie, care se prezintă structurii ierarhic superioare."),
 ("scim-profil-risc", S600, "OSGG 600/2018 art. 4 alin. (5)",
  "(5) Comisia de monitorizare analizează și prioritizează riscurile semnificative, care pot afecta atingerea obiectivelor entității publice, prin stabilirea profilului de risc și a limitei de toleranță la risc, anual, aprobate de către conducerea entității.",
  "Cine stabilește anual profilul de risc și limita de toleranță la risc, și cine le aprobă?",
  "Comisia stabilește în fiecare an profilul și pragul de toleranță pentru riscurile importante, iar conducerea entității le validează.",
  "Conducerea entității analizează și prioritizează riscurile semnificative prin stabilirea profilului de risc și a limitei de toleranță la risc, anual, aprobate de către Comisia de monitorizare.",
  "Comisia de monitorizare execută anual măsurile de control pentru riscurile semnificative ale entității publice, aprobate de către conducerea entității."),
]

def collapse(s):
    return re.sub(r"\s+", " ", s).strip()

def collapse_src(s):
    # the dumped sources mark the break between paragraphs of one article with " ... "; a span that crosses
    # paragraphs is the same text with that marker removed (nothing else is altered)
    return collapse(collapse(s).replace(" ... ", " "))

def build():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    src = {}
    out, bad = [], []
    for gid, f, label, span, q, v, wa, wx in G:
        if f not in src:
            src[f] = collapse_src(open(f, encoding="utf-8").read())
        if collapse(span) not in src[f]:
            bad.append(f"{gid}: span does not occur verbatim in {f}")
        for variant, ans, exp in (("valid", v, "accept"), ("wrong_actor", wa, "reject"), ("wrong_action", wx, "reject")):
            out.append({"id": f"{gid}--{variant}", "group": gid, "variant": variant, "expected": exp,
                        "source": label, "source_file": f, "span": collapse(span),
                        "context": collapse(span), "question": q, "proposed_answer": ans,
                        "correct_answer": v})
    if bad:
        print("BUILD REFUSED:\n  " + "\n  ".join(bad)); return 2
    with open("items_relations.jsonl", "w", encoding="utf-8") as fh:
        for o in out:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"items_relations.jsonl: {len(out)} items, {len(G)} groups, every span found verbatim in its source file")
    return 0

if __name__ == "__main__":
    sys.exit(build())
