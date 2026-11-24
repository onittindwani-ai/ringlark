"""Word and phrase tables for reading a caller. Written from general knowledge of how people refuse, ask, hedge and swear on a phone call,
plus a few common phrases in Spanish, French, Portuguese and romanised Hindi. Not taken from any test set. Plain rules, not a model.

Every pattern runs on text that was lower cased, had curly quotes straightened and accents kept.
"""

from __future__ import annotations

import re


def R(p: str) -> re.Pattern:
    return re.compile(p, re.I)


CALLWORD = R(r"\b(call(s|ed|ing)?|phone|phoning|ring(ing)?|dial(l?ing)?|robocall(s)?|rings?)\b|\b(llam|ligu|appel|telefon|t[eé]l[eé]phon|call|phone|fone)")
CHANNEL = R(
    r"\b(text(s|ing|ed)?|sms|messag(e|es|ing)|e-?mail(s|ing)?|mail(ing)?|whatsapp|voicemail)\b|"
    r"\b(consent|opt(ed)? ?out|opt me out|unsubscribe|revoke|withdraw)\b|"
    r"\b(record(ed|ing|ings)?|tape[ds]?|taping)\b|"
    r"\b(automated|auto ?dialer|robo ?calls?|robot calls?|ai calls?|prerecorded|pre-recorded|artificial)\b"
)
# the ways a person asks for the calls to stop, for good
STOP_PHRASES = [
    R(r"\b(stop|quit|cease|enough with)\s+(the |your |all )?(calling|ringing|phoning|dialing|dialling|bothering|harassing|contacting|pestering|spamming|these calls|the calls|this)\b"),
    R(r"\b(don'?t|do not|never|please don'?t|dont)\s+(ever\s+)?(call|ring|phone|contact|bother|dial|ping|reach out)\b"),
    R(r"\b(don'?t|do not|no longer|never) want (any |anymore |any more |to get |to receive |to hear (from you|more))?\s*(more |further |another |these |your |any )?(phone )?(calls?|contact|ringing|to hear)\b"),
    R(r"\b(not|to not)\s+(ever\s+)?(call|ring|phone|contact|dial|bother)\s+(me|us|this|here)\b"),
    R(r"\bno more (phone )?(calls?|contact|ringing)\b|\bno (further|future) (calls?|contact)\b|\bno calls\b"),
    R(r"\b(remov(e|ing)|delet(e|ing)|eras(e|ing)|tak(e|ing)|wip(e|ing)|dropp?(ing)?|strik(e|ing)|scrub(bing)?|get(ting)?)\s+(me|my (number|name|details|info|information|data|line)|this number|our number|us)\b.{0,40}?\b(from|off|out of)\b"),
    R(r"\btak(e|ing) (me|my number|this number|us) off\b|\bget(ting)? me off\b|\bremov(e|ing) (me|us|my number|this number)\b|\bdelet(e|ing) my (number|info|details|data)\b"),
    R(r"\b(put|add|place|list)\s+(me|my number|this number|us)\s+(on|onto|in|to)\s+(your |the |a )?(do not call|don'?t call|dnc|no.?call|block|blacklist)"),
    R(r"\bdo not call (list|registry|me|again)|\bdon'?t call (list|registry)|\bdnc\b"),
    R(r"\b(block|blacklist) (me|my number|this number)\b"),
    R(r"\b(removed|deleted|taken off|taken out|struck off|dropped|wiped)\b.{0,40}\b(list|lists|database|records|calling|register|registry)\b"),
    R(r"\bleave me alone\b|\blose my number\b|\bforget my number\b|\bget off my phone\b|\bhands off my number\b"),
    R(r"\b(i('ve| have)? (already )?(asked|told|said)( you)?( before)?( to)? ?(stop|not to call)|i said stop|i asked you to stop|how many times do i have to)\b"),
    R(r"\b(stop|quit)\b[\s.!]*$|^\W*(please )?stop( it| this| that| now| please)?\W*$"),
    # Spanish
    R(r"\bno me (llam|ll[aá]m|llames|llame|llamen)\b|\bdej(a|e|en|ar)(n)? de llamar\b|\bno vuelv(a|an|as) a llamar\b|\bno llam(es|e|en) m[aá]s\b|\b(quit|sac|borr|elimin)(a|e|en|ar)\w* (mi|el) n[uú]mero\b|\bd[eé]jenme en paz\b|\bd[eé]jame en paz\b"),
    # French
    R(r"\bne m'? ?appel(ez|le|er)? (plus|pas)\b|\bne me rappelez (plus|pas)\b|\barr[eê]t(ez|e) d'? ?appeler\b|\b(retir|supprim|enlev)(ez|er)\w* (moi|mon num[eé]ro)\b|\blaissez[- ]moi tranquille\b|\bne me t[eé]l[eé]phon"),
    # Portuguese
    R(r"\bn[aã]o me lig(ue|uem|ar)\b|\bpare de ligar\b|\bn[aã]o lig(ue|uem) (mais|de novo|novamente)\b|\b(tire|remova|apague)\w* (meu|o meu) n[uú]mero\b|\bme deixe em paz\b|\bn[aã]o quero (mais )?liga[cç][oõ]es\b"),
    # romanised Hindi
    R(r"\b(mujhe|mujhko|hume|humein|mere number pe)\b.{0,20}\b(call|phone|fone)\b.{0,12}\b(mat|na|nahi|nahin)\b|\b(call|phone|fone) (mat|na) (karo|karna|karein|kijiye|kijiyega)\b|\bmat (call|phone|fone) (karo|karna|karein|kijiye)\b|\bdobara (call|phone) (mat|na)\b|\bmera number (hata|delete|nikal|hata do)\b|\bnumber (hata|nikal) (do|dijiye)\b|\b(call|phone) band kar\b|\btang mat kar"),
]
# phrases that contain a stop word but are not a request to stop
STOP_TRAPS = [
    R(r"\b(don'?t|do not|never|please don'?t|not|won'?t|wouldn'?t|can'?t|cannot|couldn'?t|no need to|no reason to)\s+(you\s+|even\s+|ever\s+)?(stop|quit)\b"),
    R(r"\b(stop|stopped|stops|stopping)\s+(by|in|over|off|at|and (think|talk|chat|smell|look|check|ask|wonder))\b"),
    R(r"\bstop(ped)?\b[,.;]?\s+(hold on|wait|one (sec|second|moment)|hang on|let me|give me|just a|a (sec|second|moment|minute)|sorry|okay|ok)\b"),
    R(r"\b(can'?t|cannot|couldn'?t|won'?t) (help|stop) (thinking|laughing|wondering|myself)\b|\bstop me if\b|\bstop thinking\b|\b(bus|non|full|train|truck) stop\b|\bstop ?sign\b|\bstop(ped)? (the car|working|raining|breathing)\b"),
    R(r"\bif (you|i) (ever )?want(ed)? (you )?to stop\b|\bnever (said|asked|told you) (you )?to stop\b"),
]
CARRIER_WORD = R(r"^\W*(stop ?all|stop|unsubscribe|unsub|quit|cancel|end|revoke|opt ?out)\W*$")

WRONG = [
    R(r"\bwrong (number|person|guy|lady|man|woman|house|company|address|party)\b|\byou('ve| have)? (got|reached|dialed|dialled|called) the wrong\b|\bnot the (right|correct) (number|person)\b"),
    R(r"\bno ?one (here )?(by|named|called|with|at this)|\bnobody (here )?(by|with|named|called|at this)|\bthere'?s no\b.{0,25}\bhere\b|\bno such person\b|\bno .{2,25} (lives|works|here)\b"),
    R(r"\b(doesn'?t|does not|don'?t|no longer|isn'?t|not)\b.{0,12}\b(live|work|stay|reside) here\b|\b(moved|passed away|has died|died|deceased|left the company|no longer with)\b"),
    R(r"\b(never heard of|don'?t know) (him|her|them|that (person|name))\b|\bbelongs? to (someone|somebody|another|a different|somebody else)\b|\bsomeone else'?s number\b|\bthis (is|was) not (his|her|their) number\b|\b(number|line) (was|has been|got) (reassigned|changed|given to|recycled)\b|\b(i )?(just |recently )?(got|have had|had) (this|the) number\b|\bnot (him|her)\b|\b(isn'?t|is not) (him|her|that person)\b"),
    R(r"\bn[uú]mero (equivocado|errado)\b|\bfaux num[eé]ro\b|\bvous vous trompez\b|\bse equivoc|\best[aá] equivocad|\bgalat (number|jagah)\b|\bn[aã]o [eé] (esse|este) (o )?n[uú]mero\b|\bn[aã]o mora aqui\b|\bno (vive|trabaja) aqu[ií]\b|\bne (vit|travaille) pas ici\b|\bidhar (koi )?nahi\b|\bwo (yahan|yaha) nahi\b"),
]
TRANSFER = [
    R(r"\b(speak|talk|chat|connect|put|get|transfer|patch|pass|hand|forward|send|deal|see|reach|ask for|asking for|prefer|rather|rather have)\b.{0,25}\b(human|person|people|manager|supervisor|owner|someone|somebody|rep|representative|agent|receptionist|front desk|office|operator|director|boss|staff|dentist|doctor|team)\b"),
    R(r"\b(want|need|get|give|prefer|rather|like|wish|can i|could i|may i|let me|have)\b.{0,25}\b(real|live|actual) (person|human|agent|people)\b|\bhuman being\b|\b(is there|got|do you have) (a |an |any )?(human|person|manager|supervisor|someone)\b|\bput me through\b|\btransfer me\b|\bconnect me\b|\bget me (a |your |the |someone|somebody|an? )"),
    R(r"\b(hablar|habla|hable) con (una |un |el |la )?(persona|humano|gerente|supervisor|agente|alguien|encargado)\b|\b(parler|parle) [àa] (une |un |quelqu'un|une personne|un responsable|le responsable|votre responsable)\b|\bfalar com (uma |um |o |a )?(pessoa|humano|gerente|atendente|algu[eé]m)\b|\b(insaan|insan|kisi (insaan|vyakti)|manager|asli (insaan|aadmi)) (se|ko) (baat|bat)\b|\bmanager se baat\b"),
]
ROBOT = [
    R(r"\b(are|r) (you|u) (a |an |some kind of |one of those )?(real |actual |live )?(robot|bot|ai|a\.i\.|machine|computer|automated|artificial|human|person|recording|program|virtual|chatbot|chat bot)\b"),
    R(r"\bis (this|that|it) (a |an |some kind of )?(real |actual |live )?(robot|bot|ai|machine|computer|automated|human|person|recording|robocall|tape|chatbot|program)\b"),
    R(r"\b(am i|i'?m i) (talking|speaking|chatting) (to|with) (a |an )?(real |actual )?(robot|bot|machine|person|human|computer|ai|recording|something)\b|\bwho am i (talking|speaking) (to|with)\b.{0,30}\b(human|person|robot|machine|bot|real)\b"),
    R(r"\b(you |this )?(sound|sounds|sounded) (like )?(a |an )?(robot|machine|bot|recording|computer|ai|fake)\b|\bsome kind of (tape|machine|bot|robot)\b|\b(real|actual) (person|human) or\b|\b(person|human) (i'?m|i am) (talking|speaking)\b|\brobot or (a )?(human|person)\b|\b(human|person) or (a )?(robot|bot|machine|ai)\b"),
    R(r"\b(er[eo]s|es|eres) (un |una )?(robot|bot|m[aá]quina|persona|humano|grabaci[oó]n)\b|\b[¿]?(est[aá]s|es) (hablando|esto) .{0,20}(robot|grabaci[oó]n|persona real)\b|\b[êe]tes[- ]vous (un |une )?(robot|humain|vraie personne|machine|personne r[eé]elle)\b|\bc'est un robot\b|\b[eé] (um |uma )?(rob[oô]|m[aá]quina|pessoa de verdade|gravaç[aã]o|humano)\b|\b(kya|ky) (aap|tum|ye|yeh|yah) (robot|machine|insaan|insan|asli|real|bot|ai)\b|\b(robot|machine|bot) (ho|hai|hain)\b"),
]
RECORDING = [
    R(r"\b(is|are|was|will|am) (this|that|the|our|my|these|you|we|it)\b.{0,25}\b(record(ed|ing|ings)?|taped|taping|monitored|logged|transcribed|saved|stored|kept|listened)\b"),
    R(r"\b(do|does|are|will|can) (you|they|we|someone|anybody)\b.{0,15}\b(record|tape|monitor|transcribe|keep a (copy|transcript|recording)|store|save|log)\b"),
    R(r"\b(recording|recorded|transcript|transcribed|recordings)\b.{0,12}\?|\bwho (hears|listens to|has access to|gets) (this|the|these)\b.{0,25}(recording|call|chat|conversation|messages)"),
    R(r"\b(grabando|grabada|grabaci[oó]n|enregistr[eé]|enregistrement|gravando|gravada|record ho)\b"),
]
HOSTILE = R(
    r"\bvultur|\bscam(mer|mers|s)?\b|\bfraud|\bharass|\bidiot|\bstupid|\bmoron|\bpathetic|\bdisgust|\bsick of (you|this|these|it)|\bfed up\b|\bhow dare\b|\bshut (up|it)\b|\bpiss|\bbullshit|\bbull\*+|\bf+u?c?k|\bf\*+k|\bdamn\b|\bbloody\b|\bgo to hell\b|\bscum\b|\bjerk|\basshole|\bbastard|\bcrap\b|\bgarbage\b|\btrash\b|\bwaste (of|my)\b|\bwasting\b|"
    r"\bunbelievable\b|\bget lost\b|\bback off\b|\bpiss off\b|\bnuisance\b|\bterrible\b|\bannoying\b|\bannoyed\b|\bfurious\b|\bangry\b|\bnerve\b|\breport (you|this|it)|\bsue\b|\blawyer|\bcops\b|\bpolice\b|\bftc\b|\bspam\b|\bpest\b|"
    r"\bbusiness of yours\b|\bpeople like you\b|\byou people\b|\bhow many times\b|\bsick and tired\b|\bsarcas|\bwow\b.{0,40}\b(robot|call|lovely|great|nice)|\bhang(ing)? up\b|\bhung up\b|\bputting the phone down\b|\bslam"
)
CALLBACK = [
    R(r"\b(call|ring|phone|try|reach|contact|text|ping|get back to|catch|talk to|speak to|hit) (me|us)( back| again)?\b.{0,30}\b(later|tomorrow|tonight|today|this (afternoon|evening|morning|week)|next (week|month|monday|tuesday|wednesday|thursday|friday)|after|before|around|at|on|in an hour|in a few|in the (morning|afternoon|evening)|(mon|tues|wednes|thurs|fri|satur|sun)day|\d|in (january|february|march|april|may|june|july|august|september|october|november|december|the new year|spring|summer|autumn|fall|winter|a (week|month|couple|few)|(two|three|four|five|six|\d+) (days|weeks|months))|after (the )?(holidays?|christmas|easter|new year|summer|vacation|weekend|lunch|work|school)|next (year|spring|summer|autumn|fall|winter))"),
    R(r"\b(call|ring|phone|try) (me )?(back|again)\b|\bcall back\b|\bcall again\b|\btry (me )?again\b|\bcan you call (me )?(back|later)\b|\bgive me a (call|ring|buzz)\b|\bbetter (time|moment)\b|\banother time\b|\bsome other time\b|\blater (today|this|on)\b|\bcall me on\b|\breach me (on|at)\b|\bmy (cell|mobile|work|other|direct) (number|phone)?\b.{0,30}\d|\bat this number instead\b|\bcall my (cell|mobile|work|office|other)\b|\bdifferent number\b|\banother number\b"),
    R(r"\b(llam(a|e|en)(me)?|vuelv(a|e|an) a llamar) (m[aá]s tarde|ma[nñ]ana|despu[eé]s|luego)\b|\brappel(ez|e)[- ]moi (plus tard|demain)\b|\bm'? ?appel(ez|le) (plus tard|demain)\b|\bliga (mais tarde|amanh[aã]|depois)\b|\b(baad|baad mein|kal|shaam ko|subah) (call|phone|fone) (karo|kijiye|karna)\b|\bkal (call|phone) kar"),
    R(r"\btry (me )?(on |again |at |after |later|tomorrow|next)\s*((mon|tues|wednes|thurs|fri|satur|sun)day|\d|\w+)\b|\bnot (available|free|around) (on|until|before|this)\b.{0,30}\b(try|call|ring)\b"),
    R(r"\b(tomorrow|tonight|next (week|month)) (is better|works better|would be better)\b|\b(i'?m|am) (free|available|around|back) (tomorrow|later|after|on|next|from|at)\b"),
]
RUSHED = R(
    r"\b(no|not much|little|short on|out of) time\b|\b(in a|in the|at a|at the) (meeting|hurry|rush|car|middle of|appointment|session|consult|class|drive|store|shop)\b|\bbusy\b|\b(ten|10|five|5|two|2|thirty|30|a few|couple of|one|1) (seconds|minutes|min|mins)\b|\bcan'?t (talk|chat|do this|speak|really talk)\b|"
    r"\b(walk(ing)? into|driving|about to|just about|on my way|on the other line|on another call|with a (patient|client|customer))\b|\bnot a good time\b|\bbad (time|moment)\b|\bquick(ly)?\b|\bmake it (quick|short|fast)\b|\bshort version\b|\bget to the point\b|\bin a rush\b|\bi'?m rushing\b|\bgot to (run|go|dash)\b|\bhave to (run|go|dash)\b|\bwhat'?s this about\b.{0,20}\b(minute|time)\b|\b(only|just) (got|have) (a|one|two|\d)\b|\bcut to the chase\b|\bbrief(ly)?\b|\bcrazy (here|day|morning)\b|\bhectic\b|\bchaos\b|\bslammed\b|\bswamped\b"
)
NOT_INTERESTED = [
    R(r"\bnot (really )?(interested|looking|buying|in the market|a fit|for (us|me)|needed?|necessary|today|now|right now|this time)\b|\bno,? ?(thanks|thank you|thx|ta)\b|\bno interest\b|\bnot interest|\bi'?ll pass\b|\bwe'?ll pass\b|\bpass on (this|that|it)\b|\b(we|i)( are|'re|'m| am)? (all )?(set|good|fine|covered|ok|okay|sorted|happy)\b(?! to)|\bno need\b|\bdon'?t (need|want|require|use)\b|\bdo not (need|want)\b|\bnope\b|\bnah\b|\bit'?s a no\b|\bno from me\b|\bnot for me\b|\bwe have no need\b|\bno,? (not|we|i)\b|^\W*no\W*$|\bno way\b|\bnot happening\b|\bthanks,? but no\b|\bnot today\b|\bnot this (year|month|quarter)\b|\bwe'?re (not|all)\b"),
    R(r"\balready (have|use|using|work with|working with|got|signed|with|go to|see|went)\b|\b(have|got|use) (a|an|our|my|another)\b.{0,25}\b(vendor|provider|supplier|company|dentist|doctor|guy|person|contractor|agent|broker|service|software|system|team|plan|policy|membership)\b|\bhappy with (our|my|the|what)\b|\b(we|i)'?ve (got|had) (that|this|it) (covered|sorted)\b|\bin[- ]house\b|\bcontract (with|until|runs|ends)\b|\bwe just (did|signed|renewed|got|had|bought|replaced|installed)\b"),
    R(r"\btoo (expensive|much|costly|pricey|high|dear)\b|\bcan'?t afford\b|\bnot in (the|our|my) budget\b|\bpricey\b|\bcosts? too\b|\bbudget\b|\bwe'?re (tight|broke)\b|\bmoney'?s tight\b"),
    R(r"\b(send|email|mail|text|post) (me|us) (some |the |an? )?(info|information|details|brochure|something|literature|a link|link|an email|email|it over|that over|your (details|number|info)|more)\b|\bin writing\b|\b(i'?m|am|not) (not )?the (decision|one who|right person|owner|boss|person who)\b|\bnot (my|my department|my call|my decision|my area)\b|\b(talk|speak|check|run it by|ask) (to|with) my (boss|husband|wife|partner|manager|spouse|accountant|team|lawyer|dad|mum|mom)\b|\bnot the decision\b|\bdecision ?maker"),
    R(r"\b(let me|i'?ll|i will|we'?ll|we will|i need to|i have to|gotta) (think|check|ask|talk|see|look|get back|call you|ring you|consider|discuss|run|review)\b|\bmaybe (later|some ?time|next|another)\b|\b(bad|wrong|not the right) timing\b|\bnot right now\b|\bnot at the moment\b|\bnot just yet\b|\bdon'?t call (us|me) (we|i)\b|\bwho (is this|are you|gave you|told you)\b|\bhow do i know\b|\b(is this|sounds like) (a )?(legit|legitimate|real|scam|spam|sales|telemarket)\b|\bwhere did you get\b|\bhow did you (get|find)\b|\bwhat company\b|\bwho are you with\b|\bnever heard of (you|your|the company)\b|\bi don'?t (trust|believe|know you)\b|\bsounds? (suspicious|fishy|sketchy)\b|\bsales (call|pitch)\b|\btelemarket"),
]
INTEREST = [
    R(r"\b(stop|swing|drop|come|pop|walk) (by|in|over)\b|\bdon'?t stop (calling|texting|reminding|sending)\b|\bkeep (calling|texting|reminding|sending|them coming|the reminders|me posted)\b|\bi (like|love|want|need|appreciate) (the|those|your) (reminders?|calls?|texts?|updates?)\b|\bi'?m (still )?(thinking|considering) (about )?(it|booking|that)\b"),
    R(r"\b(tell|show|walk|fill) me (more|about|through|in)\b|\bsounds? (good|great|interesting|fine|perfect|useful|helpful|like a plan|worth)\b|\bi'?m (interested|intrigued|curious|keen|open|listening)\b|\bgo (ahead|on)\b|\bplease do\b|\bdefinitely\b|\babsolutely\b|\bof course\b|\bwhy not\b|\bsign me up\b|\bcount me in\b|\bi'?d (like|love|be happy|be glad) to\b|\bi would (like|love) to\b|\blet'?s (do|book|set|go|schedule|talk|try)\b|\bbook (me|it|us|that|an|a)\b|\bschedule (me|it|us|that|an|a)\b|\bset (it|that|something|me|us) up\b|\bi (want|need|would like|wanna)\b.{0,25}\b(appointment|check.?up|cleaning|quote|estimate|visit|consult|booking|demo|meeting|call|service|valuation|tour|trial|free)\b|\bbeen meaning to\b|\bperfect timing\b|\bgood timing\b|\bsort(ed)? (it )?out\b|\bthat works\b|\bworks for me\b|\bi'?m (free|available|around) (on|at|this|tomorrow|next|monday|tuesday|wednesday|thursday|friday)\b|\bwhat('?s| is) the (offer|deal|catch|special|point|pitch|proposition)\b|\bwhat (times|days|slots|openings|dates|do you have|are the options|do you offer|does it (include|cover|involve|cost|entail)|does that (include|cover|involve|entail)|is included|are the next)\b|\bwhen (can|could|are you|is the next|do you|would)\b.{0,30}\b(see|come|visit|available|free|open|book|start|get|do|schedule)\b|\bhow (does|do) (it|that|this|the) (work|go|happen)\b|\bwhat is (this|it) (about|for)\b|\bwhat'?s (this|it) (about|for|regarding)\b|\bhow long (does|would|will) (it|that|this)\b|\bis there (a|any) (discount|offer|deal|special|free)\b|\bdo you (take|accept|offer|do|have|cover)\b|\bcan you (do|help|fit|squeeze|book|come|send me the (link|details|booking))\b|\bcould you (do|help|fit|squeeze|book|come)\b|\bcan i (book|schedule|get|see|come|have|make)\b|\bsend me the (link|booking|details)\b|\bwhat would (it|that) (cost|take|involve|be)\b"),
    R(r"^\W*(yes|yeah|yep|yup|sure|please|okay sure|ok sure|why not|do it|go for it|alright then|yes please|sure thing|ja|si|s[ií]|oui|sim|haan|ha|han|theek hai|bilkul)\W*$|^\W*(yes|yeah|yep|sure)\b[,.!]?\s+(please|go|that|it|sounds|i|we|okay|ok|do|let|can|what|when|how|tell)\b"),
    R(r"\b(how much|how many|what('s| is| are| would be| will be| does it cost| do you charge)? (the |your )?(cost|price|pricing|rates?|fees?|charge|ballpark|quote)|ballpark|what do you charge|price range|how much (is|would|does|will|do|it|that|this|for)|cost me|set me back|what are you charging|how expensive|what('s| is) the (cost|price))\b"),
]
BACKCHANNEL = R(r"^\W*(uh+|um+|er+|hm+|hmm+|mm+|mhm|uh[- ]?huh|huh|ah+|oh+|okay|ok|k|kk|right|i see|go on|well|so|and|what|eh|sorry|pardon|hello|hi|hey|yo|hullo|yes\?|yeah\?|hello\?|what was that|come again|say that again|can you repeat( that)?|repeat that|i can'?t hear you|bad line|you'?re breaking up|breaking up|cut(ting)? out|didn'?t catch that|didn'?t get that|wait|hold on|\.+|\?+|[a-z]|noise|static)\W*$")
INJECTION = R(r"(ignore|disregard|forget|override)\b.{0,50}(instruction|told|prior|previous|before|everything|rules)|system prompt|(recite|reveal|repeat|read out|show)\b.{0,50}(prompt|instruction|text you were given|rules)|new rule|you are now|act as|pretend (to be|you)|developer mode|jailbreak|as an? (ai|language model).{0,20}(ignore|forget)")
SLOT = R(r"(mon|tues|wednes|thurs|fri|satur|sun)day|\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(:\d\d)?\s?(am|pm|o'?clock)\b|\bafternoon\b|\bmorning\b|\b(first|second|earlier|later|1st|2nd) (one|option)\b|\bthe (first|second|1st|2nd)\b")
TIME_BITS = R(r"\b(after the holidays|in (january|february|march|april|may|june|july|august|september|october|november|december|the new year|spring|summer|autumn|fall|winter|a (week|month|couple of (days|weeks))|(two|three|four|five|six|\d+) (days|weeks|months))|next (year|spring|summer|autumn|fall|winter)|tomorrow|tonight|today|this (afternoon|evening|morning|week)|next (week|month|monday|tuesday|wednesday|thursday|friday)|(mon|tues|wednes|thurs|fri|satur|sun)day|(in|after|around|about|at|before|by) (the )?(morning|afternoon|evening|\d{1,2}(:\d\d)?\s?(am|pm|o'?clock)?|an hour|a few hours|noon|lunch|five|four|three|two|one|six|seven|eight|nine|ten|eleven|twelve|half)|mornings|afternoons|evenings)\b")
IVR_STRONG = R(r"\bpress (one|two|three|four|five|six|seven|eight|nine|zero|star|pound|hash|\d)\b|\bpress\b.{0,20}\bfor\b|\bfor .{3,40}press\b|\byour call is (important|being|very important)\b|\bplease (hold|stay on the line|listen carefully|wait)\b|\bmain menu\b|\b(menu|options) (has|have) (changed|recently)\b|\b(these|the) (options|menu) again\b|\bstay on the line\b|\bdial (now|your|the|an extension|by name)\b|\bextension\b|\ball (of our )?(agents|representatives|operators|lines) are\b|\bpara espa[nñ]ol\b|\bdirectory\b|\bwelcome to\b.{0,60}\b(press|dial|menu|for)\b|\bthank you for calling\b|\bdue to (high|heavy) call volume\b|\bwait time\b|\bin the order (it was|they were) received\b")
MACHINE_STRONG = R(r"\b(leave|record) (a |your |me a )?(brief |short |detailed )?(message|name|number)\b|\bafter the (tone|beep|signal)\b|\bat the (tone|beep)\b|\bthe tone\b|\bvoice ?mail\b|\bmailbox\b|\bmessage (will )?be (recorded|sent)\b|\byou('ve| have) reached\b|\bplease record\b|\bnot available to (take|answer)\b|\bi'?ll get back to you\b.{0,40}\b(as soon|asap)\b|\bsorry i missed your call\b")
MACHINE_WEAK = R(r"\b(can'?t|cannot|unable to|not able to) (come to|get to|take|answer|pick up)\b|\bnot (available|here|home|in)\b|\bunavailable\b|\bnobody (is )?(available|here|home)\b|\bis not (available|taking calls)\b|\bi'?m (not )?away\b|\bbeep\b|\bwe'?re (closed|unable)\b|\bour office is closed\b|\boffice hours\b|\bcurrently (closed|unavailable)\b")

CONSENT = [
    R(r"\b(stop|quit|cease|don'?t|do not|dont|never|no more|no longer|please don'?t|enough)\b.{0,25}\b(text(s|ing)?|sms|messag(e|es|ing)|e-?mail(s|ing)?|mail(ing)?|whatsapp|record(ed|ing|ings)?|tap(e|ing)|robo ?calls?|robot calls?|automated|auto ?dialer|pre-?recorded|ai calls?)\b"),
    R(r"\b(unsubscribe|unsub|opt(ed)? ?out|opt me out|revoke|withdraw|rescind)\b"),
    R(r"\b(i )?(don'?t|do not|didn'?t|never|no)\b.{0,12}\b(consent|agree(d)? to|authori[sz]e(d)?|give (you )?permission|allow)\b|\bno consent\b|\bwithout my consent\b"),
    R(r"\b(take|remove|delete|get) (me|my (number|email|address)) (off|from|out of) (the |your |all |any )?(text|sms|email|e-mail|mailing|marketing|newsletter)\b"),
    R(r"\bno (more )?(texts?|emails?|e-mails?|messages?|sms|robo ?calls?|automated (calls?|messages?)|recording)\b"),
    R(r"\b(no me (mandes|env[ií]es|escribas)|ne m'? ?envoyez plus|n[aã]o me (mande|envie)|(message|sms|email|mail) mat (bhejo|karo|karna))\b"),
]
RECORD_ONLY = R(r"record|tape|taping|grab|enregistr|gravar|gravando")
PRICE_WORD = R(r"\b(price|prices|pricing|cost|costs|rate|rates|fee|fees|charge|charges|expensive|cheaper|discount)\b")
# an angry caller who threatens a complaint, or tells us to go away, is treated as asking to stop: one lost lead costs less than one more unwanted call
HOSTILE_STOP = R(r"\breport(ing)? (you|this|it|to|your)\b|\b(fcc|ftc|attorney general|do not call registry|regulator)\b|\b(sue|suing|lawsuit|lawyer|attorney|solicitor|police|cops)\b|\blast warning\b|\bone more call\b|\bnever quit\b|\bharass(ment|ing|ed)?\b|\bgo away\b|\bget lost\b|\b(f+u?c?k|f\*+k) ?(off|you)\b|\bpiss off\b|\bback off\b|\bscrew you\b|\bbuzz off\b|\bget off my\b|\bsick of (you|these|this)\b|\bfed up\b|\bhow many times\b|\bhang(ing)? up\b")
SPECIFIC_CHANNEL = R(r"\b(text(s|ing|ed)?|sms|e-?mail(s|ing|ed)?|mail(ing)?|whatsapp|record(ed|ing|ings)?|tap(e|ed|ing)|newsletter|voicemail)\b|\bmessages?\b")
BROAD = R(r"\beverything\b|\ball (the |of the |my |your )?(messages?|contact|communications?|forms|of it|of them|lists?|channels?)\b|\bany (contact|communications?|messages?|form|way)\b|\bautomated\b|\brobo|\brobot\b|\bauto ?dial|\bpre-?recorded\b|\bai\b|\bevery (list|channel|way)\b|\bstopall\b|\bstop all\b")
