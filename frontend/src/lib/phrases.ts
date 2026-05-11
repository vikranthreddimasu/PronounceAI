import type { Phrase } from "./types";

export const PHRASES: Phrase[] = [
  // Minimal pairs — 10
  { id: "mp-01", text: "Ship or sheep?", focus: "ɪ-vs-iː", category: "minimal-pair" },
  { id: "mp-02", text: "This is a thin thing.", focus: "ð-vs-θ", category: "minimal-pair" },
  { id: "mp-03", text: "The right light is bright.", focus: "r-vs-l", category: "minimal-pair" },
  { id: "mp-04", text: "Three free throws.", focus: "θ-vs-f", category: "minimal-pair" },
  { id: "mp-05", text: "Bed or bad? Red or rad?", focus: "ɛ-vs-æ", category: "minimal-pair" },
  { id: "mp-06", text: "Pull or pool, full or fool.", focus: "ʊ-vs-uː", category: "minimal-pair" },
  { id: "mp-07", text: "Hat, hot, height, hate.", focus: "vowel-contrasts", category: "minimal-pair" },
  { id: "mp-08", text: "Wine and vine, wet and vet.", focus: "w-vs-v", category: "minimal-pair" },
  { id: "mp-09", text: "Sue and zoo, sip and zip.", focus: "s-vs-z", category: "minimal-pair" },
  { id: "mp-10", text: "Pat, bat, mat, fat, vat.", focus: "initial-consonants", category: "minimal-pair" },

  // Phoneme drills — 15
  { id: "pd-01", text: "The weather is rather better together.", focus: "ð-medial", category: "phoneme-drill" },
  { id: "pd-02", text: "Thirty-three thousand thunderstorms.", focus: "θ-initial", category: "phoneme-drill" },
  { id: "pd-03", text: "Red lorry, yellow lorry.", focus: "r-l-cluster", category: "phoneme-drill" },
  { id: "pd-04", text: "She sells seashells by the seashore.", focus: "ʃ-vs-s", category: "phoneme-drill" },
  { id: "pd-05", text: "World, word, work, worth, worse.", focus: "ɜː-vowel", category: "phoneme-drill" },
  { id: "pd-06", text: "Very vivid video of a village.", focus: "v-initial", category: "phoneme-drill" },
  { id: "pd-07", text: "Wash, watch, want, water, walk.", focus: "w-ɒ-cluster", category: "phoneme-drill" },
  { id: "pd-08", text: "Butter, better, bitter, bottle, battle.", focus: "flap-t", category: "phoneme-drill" },
  { id: "pd-09", text: "Strength, lengths, strengths.", focus: "consonant-cluster", category: "phoneme-drill" },
  { id: "pd-10", text: "Around the rough and rugged rock.", focus: "r-color", category: "phoneme-drill" },
  { id: "pd-11", text: "Huge, human, humid, humour, hue.", focus: "hjuː-onset", category: "phoneme-drill" },
  { id: "pd-12", text: "Which witch switched which switch?", focus: "wh-vs-w", category: "phoneme-drill" },
  { id: "pd-13", text: "Autumn, often, offer, office, off.", focus: "ɒ-vs-ɔː", category: "phoneme-drill" },
  { id: "pd-14", text: "Angel, danger, change, arrange, age.", focus: "dʒ-medial", category: "phoneme-drill" },
  { id: "pd-15", text: "Think, thank, thick, thing, thought.", focus: "θ-cluster", category: "phoneme-drill" },

  // Connected speech / prosody — 15
  { id: "cs-01", text: "Can you give me a hand with this?", focus: "weak-forms", category: "connected-speech" },
  { id: "cs-02", text: "I should have told you about it.", focus: "should-have-reduction", category: "connected-speech" },
  { id: "cs-03", text: "What do you want to do tonight?", focus: "wanna-gonna", category: "connected-speech" },
  { id: "cs-04", text: "It's a matter of time before it happens.", focus: "stress-timing", category: "connected-speech" },
  { id: "cs-05", text: "The data doesn't support that conclusion.", focus: "stress-placement", category: "connected-speech" },
  { id: "cs-06", text: "I wouldn't have gone if I'd known.", focus: "conditional-reduction", category: "connected-speech" },
  { id: "cs-07", text: "We're going to need a bigger boat.", focus: "gonna-linking", category: "connected-speech" },
  { id: "cs-08", text: "Is there anything I can do to help?", focus: "intonation-rise", category: "connected-speech" },
  { id: "cs-09", text: "She asked him whether he'd already eaten.", focus: "reported-speech-rhythm", category: "connected-speech" },
  { id: "cs-10", text: "The quick brown fox jumps over the lazy dog.", focus: "full-prosody", category: "connected-speech" },
  { id: "cs-11", text: "You know what I mean? Right?", focus: "discourse-markers", category: "connected-speech" },
  { id: "cs-12", text: "I've been waiting here for nearly an hour.", focus: "present-perfect-stress", category: "connected-speech" },
  { id: "cs-13", text: "Could you possibly speak a little more slowly?", focus: "polite-intonation", category: "connected-speech" },
  { id: "cs-14", text: "Honestly, I have absolutely no idea.", focus: "emphatic-stress", category: "connected-speech" },
  { id: "cs-15", text: "Let me know if you need anything at all.", focus: "falling-intonation", category: "connected-speech" },

  // Authentic — 10
  { id: "au-01", text: "To be, or not to be — that is the question.", focus: "shakespearean-rhythm", category: "authentic" },
  { id: "au-02", text: "Ask not what your country can do for you.", focus: "jfk-cadence", category: "authentic" },
  { id: "au-03", text: "In the beginning, there was nothing.", focus: "narrative-pace", category: "authentic" },
  { id: "au-04", text: "The universe is under no obligation to make sense to you.", focus: "academic-register", category: "authentic" },
  { id: "au-05", text: "Elementary, my dear Watson.", focus: "british-rp", category: "authentic" },
  { id: "au-06", text: "Life is what happens while you're busy making other plans.", focus: "conversational", category: "authentic" },
  { id: "au-07", text: "The only way out is through.", focus: "short-emphatic", category: "authentic" },
  { id: "au-08", text: "Innovation distinguishes between a leader and a follower.", focus: "business-register", category: "authentic" },
  { id: "au-09", text: "It is a truth universally acknowledged.", focus: "austen-cadence", category: "authentic" },
  { id: "au-10", text: "We choose to go to the moon in this decade.", focus: "kennedy-prosody", category: "authentic" },
];

export const CATEGORY_LABELS: Record<Phrase["category"], string> = {
  "minimal-pair": "Minimal pair",
  "phoneme-drill": "Phoneme drill",
  "connected-speech": "Connected speech",
  "authentic": "Authentic",
};
