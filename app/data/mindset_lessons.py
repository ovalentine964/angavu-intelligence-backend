"""
Mindset Lessons Data — 56 voice lessons across 6 modules.

Based on analysis of 12 books, distilled into 56 practical lessons
for Africa's informal economy workers. Each lesson has Swahili and
English versions, with ~134 minutes total audio content.

Source books:
- The Magic of Thinking Big — David Schwartz
- Think and Grow Rich — Napoleon Hill
- The Richest Man in Babylon — George Clason
- Atomic Habits — James Clear
- The Psychology of Money — Morgan Housel
- Original content (Giving & Abundance module)

Key insight: KSh 50/day → KSh 1.1M in 20 years (compound interest)
"""

from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Module & Lesson Definitions (56 lessons across 6 modules)
# ─────────────────────────────────────────────────────────────────────────────
# Each lesson tuple: (lesson_num, title_en, title_sw, duration_min, takeaway, difficulty)

MODULE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "module_number": 1,
        "title_en": "Believe You Can",
        "title_sw": "Iniamini Unaweza",
        "source_book": "The Magic of Thinking Big — David Schwartz",
        "description_en": "Your success starts in your mind. This module rewires limiting beliefs.",
        "description_sw": "Mafanikio yako yanaanza akilini. Moduli hii inabadili imani zisizokuwa na msingi.",
        "lessons": [
            (1, "The Power of Belief", "Nguvu ya Kuamini", 2, "Success starts in your mind. What you believe, you become.", 1),
            (2, "Open the 'I Can't' Door", "Fungua Milango ya 'Siwezi'", 2, "Most limits are self-imposed. Replace 'I can't' with 'How can I?'", 1),
            (3, "Think Big", "Fikiri Kubwa", 3, "Size of thinking determines size of results. Think like the business owner you want to be.", 2),
            (4, "Words Have Power", "Neno Lina Nguvu", 2, "Your language shapes your reality. Speak abundance, not scarcity.", 1),
            (5, "Leader or Follower?", "Kiongozi ama Mfuasi?", 2, "Leaders create opportunities. Followers wait for them.", 2),
            (6, "Fear of Failure", "Woga wa Kushindwa", 3, "Failure is education, not death. Every successful person failed first.", 2),
            (7, "Story of the Dreaming Mama Mboga", "Hadithi ya Mama Mboga Mwenye Ndoto", 3, "Real story: A mama mboga who dreamed bigger and tripled her income.", 3),
            (8, "The Day to Believe", "Siku ya Kuamini", 2, "Today is the day you start believing in yourself. Not tomorrow.", 1),
            (9, "Daily Practice", "Mazoezi ya Kila Siku", 2, "Morning affirmation routine. 5 minutes that change your entire day.", 1),
        ],
    },
    {
        "module_number": 2,
        "title_en": "Think and Grow Rich",
        "title_sw": "Fikiri na Ukuwe Tajiri",
        "source_book": "Think and Grow Rich — Napoleon Hill",
        "description_en": "Napoleon Hill's 13 principles of wealth, adapted for African workers.",
        "description_sw": "Misingi 13 ya utajiri ya Napoleon Hill, iliyobadilishwa kwa wafanyakazi wa Afrika.",
        "lessons": [
            (1, "Desire", "Tamaa ya Kupata", 3, "You must want success with burning desire. Write your financial goal and read it daily.", 2),
            (2, "Faith", "Imani Inayobadilisha", 2, "Visualization of attainment. See yourself already successful.", 1),
            (3, "Auto-suggestion", "Zungumza na Nafsi Yako", 2, "Program your subconscious mind with positive financial affirmations.", 1),
            (4, "Specialized Knowledge", "Elimu Maalum", 3, "Specific knowledge earns money. Know your product better than anyone.", 2),
            (5, "Imagination", "Uundaji wa Mawazo", 2, "Synthetic and creative imagination. New ideas = new income streams.", 2),
            (6, "Organized Planning", "Mpango wa Kupanga", 3, "Desire without a plan is just a dream. Write your 90-day business plan.", 3),
            (7, "Decision", "Maamuzi ya Haraka", 2, "Decide quickly, change slowly. Indecision costs more than wrong decisions.", 1),
            (8, "Persistence", "Uvumilivu", 3, "Most people quit right before the breakthrough. Keep going.", 2),
            (9, "Master Mind", "Nguvu ya Kikundi", 2, "Surround yourself with winners. A group of 5 minds is 10x more powerful.", 2),
            (10, "Energy Direction", "Nishati ya Malengo", 2, "Channel all energy into your goals. Stop wasting energy on worry.", 1),
            (11, "Subconscious Mind", "Akili ya Ndani", 2, "Feed your mind goals, not worries. Your subconscious works on whatever you give it.", 1),
            (12, "The Brain", "Akili Yako ni Kituo", 2, "Stay tuned to positive frequencies. Avoid negative people and news.", 1),
            (13, "The Sixth Sense", "Hekima ya Muda Mrefu", 2, "Experience creates intuition. Trust your gut after you've done the work.", 2),
        ],
    },
    {
        "module_number": 3,
        "title_en": "The Richest Man in Babylon",
        "title_sw": "Mwenye Utajiri Zaidi wa Babylon",
        "source_book": "The Richest Man in Babylon — George Clason",
        "description_en": "Ancient Babylonian wealth secrets that still work today. Simple rules, massive results.",
        "description_sw": "Siri za utajiri za kale za Babeli ambazo bado zinafanya kazi leo. Sheria rahisi, matokeo makubwa.",
        "lessons": [
            (1, "The Story of Arkad", "Hadithi ya Arkad", 3, "Part of all you earn is yours to keep. Start with 10%.", 2),
            (2, "Save 10% First", "Weka Akiba Kwanza", 3, "Pay yourself first before paying anyone else. KSh 50/day = KSh 1.1M in 20 years.", 2),
            (3, "Control Expenditures", "Dhibiti Matumizi Yako", 2, "Needs vs desires. Budget doesn't mean poverty — it means control.", 1),
            (4, "Make Gold Multiply", "Fanya Pesa Ikuzalishe", 3, "Idle money wastes away. Put savings to work in a SACCO or investment.", 2),
            (5, "Guard From Loss", "Linda Mali Zako", 2, "Protect principal first. Don't gamble with money you can't afford to lose.", 1),
            (6, "Profitable Dwelling", "Nyumba Yako ni Biashara", 2, "Make your space profitable. Can your kiosk also charge phones?", 2),
            (7, "Insure Future Income", "Bima ya Kesho", 3, "Plan for old age and emergencies. NHIF, emergency fund, children's education.", 2),
            (8, "Increase Ability to Earn", "Ongeza Uwezo Wako", 3, "Invest in yourself. Learn a new skill. Better skills = more income.", 2),
            (9, "The Chariot Maker", "Hadithi ya Mtu wa Magari", 2, "Working hard isn't enough. Work smart AND hard.", 1),
        ],
    },
    {
        "module_number": 4,
        "title_en": "Atomic Habits",
        "title_sw": "Tabia Ndogo, Matokeo Makubwa",
        "source_book": "Atomic Habits — James Clear",
        "description_en": "Tiny changes, remarkable results. Build wealth habits that stick.",
        "description_sw": "Mabadiliko madogo, matokeo ya ajabu. Jenga tabia za utajiri zinazodumu.",
        "lessons": [
            (1, "1% Daily Improvement", "1% Kila Siku", 2, "Small changes compound dramatically. 1% better daily = 37x better in a year.", 1),
            (2, "Identity-Based Habits", "Mimi Ni Mtu Gani?", 3, "Focus on who you want to become, not what you want to achieve. 'I am a saver.'", 2),
            (3, "Make It Obvious", "Fanya Ionekane", 2, "Make desired behavior visible. Put your savings jar where you can see it.", 1),
            (4, "Make It Attractive", "Fanya Ivutie", 2, "Pair habits with enjoyment. Save while listening to music you love.", 1),
            (5, "Make It Easy", "Fanya Rahisi", 2, "Reduce friction for good habits. M-Pesa auto-save, not manual transfers.", 1),
            (6, "Make It Satisfying", "Fanya Irithishe", 2, "Immediate rewards reinforce habits. Celebrate every KSh 100 saved.", 1),
            (7, "Habit Stacking", "Mnyororo wa Tabia", 3, "After X, I will do Y. Link new habits to existing routines.", 2),
            (8, "Breaking Bad Habits", "Kuvunja Tabia Mbaya", 3, "Invert the 4 laws: make it invisible, unattractive, difficult, unsatisfying.", 2),
            (9, "Money Garden Game", "Bustani ya Pesa Yako", 2, "Visualize your financial growth like a garden. Each seed is a shilling saved.", 1),
        ],
    },
    {
        "module_number": 5,
        "title_en": "Psychology of Money",
        "title_sw": "Saikolojia ya Pesa",
        "source_book": "The Psychology of Money — Morgan Housel",
        "description_en": "Understanding your relationship with money is the key to wealth.",
        "description_sw": "Kuelewa uhusiano wako na pesa ndio ufunguo wa utajiri.",
        "lessons": [
            (1, "Compounding", "Nguvu ya Kuzaliana", 3, "Time in market beats timing the market. KSh 50/day → KSh 1.1M in 20 years.", 2),
            (2, "Room for Error", "Nafasi ya Makosa", 2, "Survive bad times to enjoy good times. Always have an emergency fund.", 1),
            (3, "Wealth Is What You Don't Spend", "Utajiri ni Kile Usichotumia", 3, "True wealth is invisible. The richest person is the one who needs least.", 2),
            (4, "Reasonable > Rational", "Wastani Bora Zaidi ya Kamili", 2, "Good enough consistently beats perfect occasionally. Save consistently.", 1),
            (5, "Seduction of Pessimism", "Uvivu wa Pesimism", 2, "Pessimism sounds smart but optimism wins. Believe in your future.", 1),
            (6, "Nothing Is Free", "Hakuna Kitu Bure", 2, "Every decision has a hidden cost. Free things often cost the most.", 1),
            (7, "Freedom Is True Wealth", "Uhuru ni Utajiri Halisi", 3, "Wealth = freedom of time. Money buys options, not things.", 2),
            (8, "Save Without a Reason", "Hifadhi Bila Sababu", 2, "Save for options, not just goals. Unknown opportunities need capital.", 1),
        ],
    },
    {
        "module_number": 6,
        "title_en": "Giving and Abundance",
        "title_sw": "Kutoa na Wingi",
        "source_book": "Original content — spiritual/philosophical foundation",
        "description_en": "The paradox of wealth: giving creates more. Build an abundant mindset.",
        "description_sw": "Kitendawili cha utajiri: kutoa kunatengeneza zaidi. Jenga akili ya wingi.",
        "lessons": [
            (1, "The Secret of Giving", "Siri ya Kutoa", 3, "Giving opens the hand to receive. Tight fist can neither give nor receive.", 2),
            (2, "Tithe and Taxes", "Zaka na Ushuru", 2, "Systematic proportional giving builds trust and abundance.", 1),
            (3, "Giving Creates Space", "Kutoa kunatengeneza Nafasi", 2, "Abundance follows generosity. Make room for more by releasing some.", 1),
            (4, "True Generosity", "Ukarimu wa Kweli", 2, "Give from the heart, not obligation. Joyful giving multiplies returns.", 1),
            (5, "The Abundance Cycle", "Mzunguko wa Wingi", 3, "Income and giving grow together. Track your giving and watch income rise.", 2),
            (6, "Wise Giving", "Kutoa kwa Busara", 2, "Strategic, not reckless, generosity. Give where it creates the most impact.", 2),
            (7, "Story of the Giver", "Hadithi ya Mtoaji", 3, "Real transformation: A boda boda rider who gave first and earned 3x more.", 3),
            (8, "End of Journey — New Beginning", "Mwisho wa Safari — Mwanzo Mpya", 3, "This is just the beginning. Apply all 56 lessons and transform your life.", 2),
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Daily Affirmations (from each book)
# ─────────────────────────────────────────────────────────────────────────────

AFFIRMATIONS: list[dict[str, str]] = [
    # Magic of Thinking Big
    {
        "text_en": "I believe in myself and my ability to succeed. My mind is powerful.",
        "text_sw": "Ninaamini katika nafsi yangu na uwezo wangu wa kufanikiwa. Akili yangu ni yenye nguvu.",
        "category": "belief",
        "source_book": "The Magic of Thinking Big",
    },
    {
        "text_en": "I think big. My goals are large and my actions match my ambitions.",
        "text_sw": "Ninakubwa kufikiri. Malengo yangu ni makubwa na matendo yangu yanalingana na ndoto zangu.",
        "category": "belief",
        "source_book": "The Magic of Thinking Big",
    },
    {
        "text_en": "I replace 'I can't' with 'How can I?' Every problem has a solution.",
        "text_sw": "Ninabadili 'Siwezi' kuwa 'Ninawezaje?' Kila tatizo lina suluhisho.",
        "category": "belief",
        "source_book": "The Magic of Thinking Big",
    },
    {
        "text_en": "I am a leader. I create opportunities instead of waiting for them.",
        "text_sw": "Mimi ni kiongozi. Ninatengeneza fursa badala ya kuzisubiri.",
        "category": "belief",
        "source_book": "The Magic of Thinking Big",
    },
    {
        "text_en": "Failure is my teacher, not my enemy. I learn and grow from every setback.",
        "text_sw": "Kushindwa ni mwalimu wangu, si adui yangu. Ninajifunza na kukua kutokana na kila changamoto.",
        "category": "belief",
        "source_book": "The Magic of Thinking Big",
    },
    # Think and Grow Rich
    {
        "text_en": "I desire wealth with burning passion. My financial goal is clear and written.",
        "text_sw": "Natamani utajiri kwa shauku inayowaka. Lengo langu la kifedha liko wazi na limeandikwa.",
        "category": "wealth",
        "source_book": "Think and Grow Rich",
    },
    {
        "text_en": "I have faith in my ability to become wealthy. I see myself already successful.",
        "text_sw": "Nina imani katika uwezo wangu wa kuwa tajiri. Ninajiona nikiwa nimefanikiwa tayari.",
        "category": "wealth",
        "source_book": "Think and Grow Rich",
    },
    {
        "text_en": "I decide quickly and act with confidence. Indecision costs more than wrong decisions.",
        "text_sw": "Ninafanya maamuzi haraka na kwa uhakika. Kutofanya maamuzi kunagharamia zaidi ya maamuzi mabaya.",
        "category": "wealth",
        "source_book": "Think and Grow Rich",
    },
    {
        "text_en": "I persist until I succeed. I never quit right before my breakthrough.",
        "text_sw": "Ninavumilia mpaka nifanikiwe. Sijawahi kuacha kabla ya mafanikio yangu.",
        "category": "wealth",
        "source_book": "Think and Grow Rich",
    },
    {
        "text_en": "I surround myself with people who lift me up. My mastermind group is powerful.",
        "text_sw": "Ninajizungusha na watu wanaoninua. Kikundi changu cha akili ni chenye nguvu.",
        "category": "wealth",
        "source_book": "Think and Grow Rich",
    },
    # Richest Man in Babylon
    {
        "text_en": "I pay myself first. At least 10% of everything I earn is mine to keep.",
        "text_sw": "Ninajilipa kwanza. Angalau 10% ya kila kitu ninachopata ni changu kuhifadhi.",
        "category": "savings",
        "source_book": "The Richest Man in Babylon",
    },
    {
        "text_en": "I control my expenditures. I distinguish between needs and desires.",
        "text_sw": "Ninadhibiti matumizi yangu. Ninatofautisha mahitaji na matakwa.",
        "category": "savings",
        "source_book": "The Richest Man in Babylon",
    },
    {
        "text_en": "My money works for me. Every shilling saved is a seed that grows.",
        "text_sw": "Pesa yangu inafanya kazi kwa ajili yangu. Kila shilingi iliyohifadhiwa ni mbegu inayokua.",
        "category": "savings",
        "source_book": "The Richest Man in Babylon",
    },
    {
        "text_en": "I protect my money from loss. I invest wisely, not recklessly.",
        "text_sw": "Ninapesa yangu dhidi ya hasara. Ninawekeza kwa busara, si kwa upuuzi.",
        "category": "savings",
        "source_book": "The Richest Man in Babylon",
    },
    {
        "text_en": "I invest in myself. My ability to earn grows every day.",
        "text_sw": "Ninajitolea katika nafsi yangu. Uwezo wangu wa kupata unaongezeka kila siku.",
        "category": "savings",
        "source_book": "The Richest Man in Babylon",
    },
    # Atomic Habits
    {
        "text_en": "I am 1% better today than yesterday. Small improvements lead to massive results.",
        "text_sw": "Niko bora 1% leo kuliko jana. Maboresho madogo yanasababisha matokeo makubwa.",
        "category": "habits",
        "source_book": "Atomic Habits",
    },
    {
        "text_en": "I am a person who saves. This is who I am, not just what I do.",
        "text_sw": "Mimi ni mtu anayehifadhi. Hii ndio mimi, si tu kile ninachofanya.",
        "category": "habits",
        "source_book": "Atomic Habits",
    },
    {
        "text_en": "I make good habits easy and bad habits hard. My environment supports my success.",
        "text_sw": "Ninajenga tabia nzuri kuwa rahisi na tabia mbaya kuwa ngumu. Mazingira yangu yanafanikia.",
        "category": "habits",
        "source_book": "Atomic Habits",
    },
    {
        "text_en": "After I count my morning stock, I record yesterday's sales. This is my habit chain.",
        "text_sw": "Baada ya kuhesabu hisa yangu ya asubuhi, ninarekodi mauzo ya jana. Hii ndio minyororo ya tabia yangu.",
        "category": "habits",
        "source_book": "Atomic Habits",
    },
    {
        "text_en": "I celebrate every small win. Every KSh 100 saved is a victory worth noting.",
        "text_sw": "Ninasherehekea kila ushindi mdogo. Kila KSh 100 iliyohifadhiwa ni ushindi wa kusherehekewa.",
        "category": "habits",
        "source_book": "Atomic Habits",
    },
    # Psychology of Money
    {
        "text_en": "KSh 50 saved daily becomes KSh 1.1 million in 20 years. Time is my greatest ally.",
        "text_sw": "KSh 50 zilizohifadhiwa kila siku zinakuwa KSh 1.1 milioni katika miaka 20. Muda ni rafiki yangu mkubwa.",
        "category": "compound",
        "source_book": "The Psychology of Money",
    },
    {
        "text_en": "True wealth is what I don't spend. My savings are my secret power.",
        "text_sw": "Utajiri halisi ni kile situmii. Akiba yangu ni nguvu yangu ya siri.",
        "category": "compound",
        "source_book": "The Psychology of Money",
    },
    {
        "text_en": "I save without needing a specific reason. Options are the highest form of wealth.",
        "text_sw": "Ninahifadhi bila sababu maalum. Chaguo ndio kiwango cha juu cha utajiri.",
        "category": "compound",
        "source_book": "The Psychology of Money",
    },
    {
        "text_en": "Wealth buys freedom, not things. My goal is control over my time.",
        "text_sw": "Utajiri hununua uhuru, si vitu. Lengo langu ni udhibiti wa wakati wangu.",
        "category": "compound",
        "source_book": "The Psychology of Money",
    },
    {
        "text_en": "I stay optimistic about my financial future. Pessimism is expensive.",
        "text_sw": "Ninafuatilia matumaini ya siku zijazo za kifedha yangu. Pesimism ni ghali.",
        "category": "compound",
        "source_book": "The Psychology of Money",
    },
    # Giving & Abundance
    {
        "text_en": "I give generously and receive abundantly. My open hand attracts blessings.",
        "text_sw": "Ninatoa kwa ukarimu na napokea kwa wingi. Mkono wangu wazi unavutia baraka.",
        "category": "giving",
        "source_book": "Giving and Abundance",
    },
    {
        "text_en": "Giving creates space for more. I am not diminished by generosity — I am expanded.",
        "text_sw": "Kutoa kunatengeneza nafasi kwa zaidi. Sipunguzwi na ukarimu — Nimepanuliwa.",
        "category": "giving",
        "source_book": "Giving and Abundance",
    },
    {
        "text_en": "I give from joy, not obligation. Cheerful giving multiplies my returns.",
        "text_sw": "Ninatoa kwa furaha, si kwa lazima. Kutoa kwa furaha kunazidisha mapato yangu.",
        "category": "giving",
        "source_book": "Giving and Abundance",
    },
    {
        "text_en": "My income grows as I give more. The abundance cycle flows through me.",
        "text_sw": "Mapato yangu yanaongezeka ninapotoa zaidi. Mzunguko wa wingi unapita kupitia kwangu.",
        "category": "giving",
        "source_book": "Giving and Abundance",
    },
    {
        "text_en": "I give wisely and strategically. My generosity creates maximum impact.",
        "text_sw": "Ninatoa kwa busara na kimkakati. Ukarimu wangu unaunda athari kubwa.",
        "category": "giving",
        "source_book": "Giving and Abundance",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Habit Stacking Formulas per Worker Type
# ─────────────────────────────────────────────────────────────────────────────

HABIT_STACKS: dict[str, dict[str, Any]] = {
    "mama_mboga": {
        "worker_type": "mama_mboga",
        "name_en": "Mama Mboga Daily Stack",
        "name_sw": "Mnyororo wa Mama Mboga wa Kila Siku",
        "description_en": "Morning-to-evening habit chain for vegetable vendors",
        "description_sw": "Minyororo ya tabia za asubuhi hadi jioni kwa wachuuzi wa mboga",
        "stack": [
            {"time": "05:30", "habit_en": "Wake up and say affirmation", "habit_sw": "Amka na useme uthibitisho", "points": 5},
            {"time": "06:00", "habit_en": "Check stock and count inventory", "habit_sw": "Angalia hesabu na uheshabu hisa", "points": 10},
            {"time": "06:30", "habit_en": "Set today's sales goal (write it down)", "habit_sw": "Weka lengo la mauzo ya leo (liandike)", "points": 5},
            {"time": "07:00", "habit_en": "Open shop — start selling", "habit_sw": "Fungua duka — anza kuuza", "points": 0},
            {"time": "12:00", "habit_en": "Midday: Record morning sales in notebook", "habit_sw": "Katikati ya siku: Rekodi mauzo ya asubuhi", "points": 10},
            {"time": "17:00", "habit_en": "Count today's earnings", "habit_sw": "Hesabu mapato ya leo", "points": 10},
            {"time": "17:15", "habit_en": "Save 10% via M-Pesa (pay yourself first)", "habit_sw": "Hifadhi 10% kupitia M-Pesa (jilipe kwanza)", "points": 15},
            {"time": "17:30", "habit_en": "Record all expenses in ledger", "habit_sw": "Rekodi matumizi yote katika daftari", "points": 10},
            {"time": "18:00", "habit_en": "Listen to 1 mindset lesson (2-3 min)", "habit_sw": "Sikiliza somo 1 la akili (dakika 2-3)", "points": 10},
            {"time": "19:00", "habit_en": "Review today: What went well? What to improve?", "habit_sw": "Fikiria leo: Kilikuwa vizuri? Nini kuboreshwa?", "points": 5},
            {"time": "20:00", "habit_en": "Help one fellow mama mboga with advice", "habit_sw": "Msaidie mama mboga mwenye ushauri", "points": 10},
            {"time": "21:00", "habit_en": "Sleep debt-free: no borrowing today", "habit_sw": "Lala bila deni: hakuna kukopa leo", "points": 20},
        ],
        "daily_affirmation_sw": "Mimi ni mama mboga mwenye ndoto kubwa. Biashara yangu inakua kila siku.",
        "daily_affirmation_en": "I am a mama mboga with big dreams. My business grows every day.",
    },
    "boda_boda": {
        "worker_type": "boda_boda",
        "name_en": "Boda Boda Rider Stack",
        "name_sw": "Mnyororo wa Mpanda Boda Boda",
        "description_en": "Habit chain for motorcycle taxi riders",
        "description_sw": "Minyororo ya tabia kwa waendesha pikipiki",
        "stack": [
            {"time": "05:30", "habit_en": "Wake up, say: 'I am building wealth, not just earning'", "habit_sw": "Amka, useme: 'Ninajenga utajiri, si tu kupata'", "points": 5},
            {"time": "06:00", "habit_en": "Check motorcycle condition (saves repair costs)", "habit_sw": "Angalia hali ya pikipiki (hifadhi gharama za ukarabati)", "points": 10},
            {"time": "06:15", "habit_en": "Set daily earnings target", "habit_sw": "Weka lengo la mapato ya kila siku", "points": 5},
            {"time": "06:30", "habit_en": "Start riding — every trip is a transaction to record", "habit_sw": "Anza kupanda — kila safari ni muamala wa kurekodi", "points": 0},
            {"time": "12:00", "habit_en": "Lunch break: Count morning earnings", "habit_sw": "Mapumziko ya chakula: Hesabu mapato ya asubuhi", "points": 10},
            {"time": "17:00", "habit_en": "Record total daily earnings and fuel cost", "habit_sw": "Rekodi mapato ya siku na gharama ya mafuta", "points": 10},
            {"time": "17:15", "habit_en": "Save 10% before spending on anything else", "habit_sw": "Hifadhi 10% kabla ya kutumia chochote kingine", "points": 15},
            {"time": "17:30", "habit_en": "Track all expenses: fuel, food, repairs", "habit_sw": "Fuatilia matumizi yote: mafuta, chakula, ukarabati", "points": 10},
            {"time": "18:00", "habit_en": "Listen to mindset lesson while resting", "habit_sw": "Sikiliza somo la akili ukipumzika", "points": 10},
            {"time": "19:00", "habit_en": "Review: Did I hit my target? What can improve?", "habit_sw": "Fikiria: Nilifikia lengo langu? Nini kuboreshwa?", "points": 5},
            {"time": "20:00", "habit_en": "Help a fellow rider (share a tip or customer)", "habit_sw": "Msaidie mwenzako (shiriki neno au mteja)", "points": 10},
            {"time": "21:00", "habit_en": "No debt today = full points. Sleep well.", "habit_sw": "Hakuna deni leo = pointi kamili. Lala vizuri.", "points": 20},
        ],
        "daily_affirmation_sw": "Kila safari inaniweka karibu na lengo langu. Muda wangu ni pesa, na ninaitumia vizuri.",
        "daily_affirmation_en": "Every trip brings me closer to my goal. My time is money, and I use it well.",
    },
    "duka_owner": {
        "worker_type": "duka_owner",
        "name_en": "Duka Owner Stack",
        "name_sw": "Mnyororo wa Mmiliki wa Duka",
        "description_en": "Habit chain for shop/dukawallah owners",
        "description_sw": "Minyororo ya tabia kwa wamiliki wa maduka",
        "stack": [
            {"time": "06:00", "habit_en": "Morning affirmation: 'My duka is growing into an empire'", "habit_sw": "Uthibitisho wa asubuhi: 'Duka langu linakuwa ufalme'", "points": 5},
            {"time": "06:30", "habit_en": "Inventory check — note items running low", "habit_sw": "Angalia hisa — andika vitu vinavyopungua", "points": 10},
            {"time": "07:00", "habit_en": "Set daily revenue target (write on board)", "habit_sw": "Weka lengo la mapato ya siku (andika ubaoni)", "points": 5},
            {"time": "07:30", "habit_en": "Open shop — every customer is a learning opportunity", "habit_sw": "Fungua duka — kila mteja ni fursa ya kujifunza", "points": 0},
            {"time": "13:00", "habit_en": "Midday sales check — are we on target?", "habit_sw": "Angalia mauzo ya katikati — tuko kwenye lengo?", "points": 10},
            {"time": "18:00", "habit_en": "Close day: Record all sales and expenses", "habit_sw": "Funga siku: Rekodi mauzo na matumizi yote", "points": 10},
            {"time": "18:15", "habit_en": "Save 10% of profit (separate from capital)", "habit_sw": "Hifadhi 10% ya faida (tofauti na mtaji)", "points": 15},
            {"time": "18:30", "habit_en": "Review slow-moving stock — plan promotions", "habit_sw": "Fikiria hisa zisizotembea — panga matangazo", "points": 10},
            {"time": "19:00", "habit_en": "Listen to mindset lesson (2-3 min)", "habit_sw": "Sikiliza somo la akili (dakika 2-3)", "points": 10},
            {"time": "19:30", "habit_en": "Analyze: Which products are most profitable?", "habit_sw": "Chambua: Bidhaa gani zina faida zaidi?", "points": 5},
            {"time": "20:00", "habit_en": "Share business tip with neighboring duka owner", "habit_sw": "Shiriki neno la biashara na mmiliki wa duka jirani", "points": 10},
            {"time": "21:00", "habit_en": "Zero debt today. Protect your capital.", "habit_sw": "Deni sifuri leo. Linda mtaji wako.", "points": 20},
        ],
        "daily_affirmation_sw": "Duka langu ni biashara inayokua. Kila siku ninajifunza na kuboresha.",
        "daily_affirmation_en": "My duka is a growing business. Every day I learn and improve.",
    },
    "mitumba_vendor": {
        "worker_type": "mitumba_vendor",
        "name_en": "Mitumba Vendor Stack",
        "name_sw": "Mnyororo wa Muuzaji wa Mitumba",
        "description_en": "Habit chain for second-hand clothing vendors",
        "description_sw": "Minyororo ya tabia kwa wachuuzi wa mitumba",
        "stack": [
            {"time": "05:00", "habit_en": "Affirmation: 'I see value where others see waste'", "habit_sw": "Uthibitisho: 'Ninaona thamani ambapo wengine wanaona taka'", "points": 5},
            {"time": "05:30", "habit_en": "Sort and price new stock", "habit_sw": "Panga na weka bei za hisa mpya", "points": 10},
            {"time": "06:00", "habit_en": "Set daily target — how many pieces to sell?", "habit_sw": "Weka lengo la siku — vipande vingapi kuuza?", "points": 5},
            {"time": "07:00", "habit_en": "Display best items prominently", "habit_sw": "Onyesha vitu bora zaidi mahali pazuri", "points": 0},
            {"time": "12:00", "habit_en": "Count morning sales and record", "habit_sw": "Hesabu mauzo ya asubuhi na urekodi", "points": 10},
            {"time": "17:00", "habit_en": "Total day's earnings and record", "habit_sw": "Jumlisha mapato ya siku na urekodi", "points": 10},
            {"time": "17:15", "habit_en": "Save 10% before touching anything else", "habit_sw": "Hifadhi 10% kabla ya kugusa chochote kingine", "points": 15},
            {"time": "17:30", "habit_en": "Record all expenses: transport, food, market fee", "habit_sw": "Rekodi matumizi yote: usafiri, chakula, ada ya soko", "points": 10},
            {"time": "18:00", "habit_en": "Learn: What sold best today? Why?", "habit_sw": "Jifunze: Nini kiliuzwa vizuri zaidi leo? Kwa nini?", "points": 10},
            {"time": "19:00", "habit_en": "Listen to mindset lesson", "habit_sw": "Sikiliza somo la akili", "points": 10},
            {"time": "20:00", "habit_en": "Help another vendor with a selling tip", "habit_sw": "Msaidie muuzaji mwingine na neno la kuuza", "points": 10},
            {"time": "21:00", "habit_en": "No debt today. Protect your profit.", "habit_sw": "Hakuna deni leo. Linda faida yako.", "points": 20},
        ],
        "daily_affirmation_sw": "Kila kitu kina thamani. Mimi ni mtaalamu wa kuona fursa zilizofichwa.",
        "daily_affirmation_en": "Everything has value. I am an expert at seeing hidden opportunities.",
    },
    "mkono_worker": {
        "worker_type": "mkono_worker",
        "name_en": "Jua Kali / Casual Worker Stack",
        "name_sw": "Mnyororo wa Mfanyakazi wa Mikono",
        "description_en": "Habit chain for manual/casual laborers",
        "description_sw": "Minyororo ya tabia kwa wafanyakazi wa mikono",
        "stack": [
            {"time": "05:30", "habit_en": "Affirmation: 'My hands create value. I invest in my future.'", "habit_sw": "Uthibitisho: 'Mikono yangu inatengeneza thamani. Ninawekeza kwa siku zijazo.'", "points": 5},
            {"time": "06:00", "habit_en": "Prepare for work — be early, be reliable", "habit_sw": "Jitayarishe kwa kazi — kuwa mapema, kuwa wa kutegemewa", "points": 5},
            {"time": "12:00", "habit_en": "Lunch: Remember — this energy is an investment in earning", "habit_sw": "Chakula: Kumbuka — nguvu hii ni uwekezaji katika mapato", "points": 0},
            {"time": "17:00", "habit_en": "Receive pay and immediately save 10%", "habit_sw": "Pokea mshahara na mara moja hifadhi 10%", "points": 15},
            {"time": "17:15", "habit_en": "Record today's earnings in phone notebook", "habit_sw": "Rekodi mapato ya leo katika daftari la simu", "points": 10},
            {"time": "17:30", "habit_en": "Track expenses: transport, food, water", "habit_sw": "Fuatilia matumizi: usafiri, chakula, maji", "points": 10},
            {"time": "18:00", "habit_en": "Learn one new skill (YouTube, practice, ask someone)", "habit_sw": "Jifunze ujuzi mpya mmoja (YouTube, mazoezi, uliza mtu)", "points": 10},
            {"time": "19:00", "habit_en": "Listen to mindset lesson", "habit_sw": "Sikiliza somo la akili", "points": 10},
            {"time": "19:30", "habit_en": "Review: Am I building skills or just trading time?", "habit_sw": "Fikiria: Ninajenga ujuzi au ninabadilisha wakati tu?", "points": 5},
            {"time": "20:00", "habit_en": "Encourage a fellow worker", "habit_sw": "Himiza mfanyakazi mwenzako", "points": 10},
            {"time": "21:00", "habit_en": "Stay debt-free. Every shilling saved is a step up.", "habit_sw": "Kaa bila deni. Kila shilingi iliyohifadhiwa ni hatua juu.", "points": 20},
        ],
        "daily_affirmation_sw": "Kazi yangu ya mikono ni ya heshima. Ninajenga utajiri hatua kwa hatua.",
        "daily_affirmation_en": "My manual work is honorable. I build wealth step by step.",
    },
    "beautician": {
        "worker_type": "beautician",
        "name_en": "Salon/Barbershop Stack",
        "name_sw": "Mnyororo wa Saluni/Upasuaji",
        "description_en": "Habit chain for salon and barbershop workers",
        "description_sw": "Minyororo ya tabia kwa wafanyakazi wa saluni na kinyozi",
        "stack": [
            {"time": "07:00", "habit_en": "Affirmation: 'My creativity is my wealth. Each client is an opportunity.'", "habit_sw": "Uthibitisho: 'Ubunifu wangu ni utajiri wangu. Kila mteja ni fursa.'", "points": 5},
            {"time": "07:30", "habit_en": "Prepare workspace — cleanliness builds trust", "habit_sw": "Tayarisha mahali pa kazi — usafi unajenga uaminifu", "points": 10},
            {"time": "08:00", "habit_en": "Set daily earnings target", "habit_sw": "Weka lengo la mapato ya siku", "points": 5},
            {"time": "08:30", "habit_en": "Open for clients — offer extra service to each one", "habit_sw": "Fungua kwa wateja — toa huduma ya ziada kwa kila mmoja", "points": 0},
            {"time": "13:00", "habit_en": "Lunch break: Count morning earnings", "habit_sw": "Mapumziko ya chakula: Hesabu mapato ya asubuhi", "points": 10},
            {"time": "18:00", "habit_en": "Close: Record all earnings and product costs", "habit_sw": "Funga: Rekodi mapato na gharama za bidhaa", "points": 10},
            {"time": "18:15", "habit_en": "Save 10% via M-Pesa before spending", "habit_sw": "Hifadhi 10% kupitia M-Pesa kabla ya kutumia", "points": 15},
            {"time": "18:30", "habit_en": "Record expenses: products, rent, electricity", "habit_sw": "Rekodi matumizi: bidhaa, kodi, umeme", "points": 10},
            {"time": "19:00", "habit_en": "Learn: Watch one technique video or practice a new style", "habit_sw": "Jifunze: Tazama video moja ya mbinu au fanya mtindo mpya", "points": 10},
            {"time": "19:30", "habit_en": "Listen to mindset lesson", "habit_sw": "Sikiliza somo la akili", "points": 10},
            {"time": "20:00", "habit_en": "Help a colleague improve their craft", "habit_sw": "Msaidie mwenzako kuboresha ujuzi wake", "points": 10},
            {"time": "21:00", "habit_en": "Zero debt today. Your skills are your capital.", "habit_sw": "Deni sifuri leo. Ujuzi wako ni mtaji wako.", "points": 20},
        ],
        "daily_affirmation_sw": "Ubunifu wangu unavutia wateja na utajiri. Kila siku ninakuwa bora zaidi.",
        "daily_affirmation_en": "My creativity attracts clients and wealth. Every day I become better.",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Compound Interest Story (KSh 50/day → KSh 1.1M)
# ─────────────────────────────────────────────────────────────────────────────

COMPOUND_INTEREST_STORY = {
    "title_en": "The KSh 50 Miracle",
    "title_sw": "Miujiza ya KSh 50",
    "story_en": (
        "Imagine you save KSh 50 every day. That's less than a cup of tea. "
        "In one month, you have KSh 1,500. In one year, KSh 18,250. "
        "But here's the magic: if you put that money in a SACCO earning 10% per year, "
        "in 20 years you'll have KSh 1,100,000. Over one million shillings! "
        "The money makes babies, and those babies make more babies. "
        "That's compound interest — the eighth wonder of the world. "
        "Start today. Not tomorrow. Today."
    ),
    "story_sw": (
        "Fikiria unahifadhi KSh 50 kila siku. Ni chini ya kikombe cha chai. "
        "Katika mwezi mmoja, una KSh 1,500. Katika mwaka mmoja, KSh 18,250. "
        "Lakini ndio uchawi: ukiiweka pesa hiyo katika SACCO inayopata 10% kwa mwaka, "
        "katika miaka 20 utakuwa na KSh 1,100,000. Zaidi ya shilingi milioni moja! "
        "Pesa inazaa watoto, na watoto hao wanazaa watoto zaidi. "
        "Hivyo ndivyo riba inavyofanya — muujiza wa nane wa dunia. "
        "Anza leo. Si kesho. Leo."
    ),
    "daily_savings": 50,
    "annual_interest_rate": 0.10,
    "years": 20,
    "final_amount": 1_100_000,
}


def get_all_lessons() -> list[dict[str, Any]]:
    """Return all 56 lessons as flat list of dicts."""
    lessons = []
    order_index = 1
    for module in MODULE_DEFINITIONS:
        for lesson_num, title_en, title_sw, duration, takeaway, difficulty in module["lessons"]:
            lessons.append({
                "module_number": module["module_number"],
                "lesson_number": lesson_num,
                "title_en": title_en,
                "title_sw": title_sw,
                "source_book": module["source_book"],
                "key_takeaway": takeaway,
                "duration_minutes": duration,
                "difficulty": difficulty,
                "order_index": order_index,
            })
            order_index += 1
    return lessons


def get_all_affirmations() -> list[dict[str, str]]:
    """Return all affirmations."""
    return AFFIRMATIONS


def get_affirmations_by_category(category: str) -> list[dict[str, str]]:
    """Return affirmations filtered by category."""
    return [a for a in AFFIRMATIONS if a["category"] == category]


def get_affirmation_by_index(index: int) -> dict[str, str]:
    """Get affirmation by index (cycling through for daily rotation)."""
    return AFFIRMATIONS[index % len(AFFIRMATIONS)]


def get_habit_stack(worker_type: str) -> dict[str, Any] | None:
    """Get habit stacking formula for a worker type."""
    return HABIT_STACKS.get(worker_type)


def get_all_worker_types() -> list[str]:
    """Return all available worker types for habit stacking."""
    return list(HABIT_STACKS.keys())
