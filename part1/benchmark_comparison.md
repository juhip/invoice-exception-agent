# Two tests, one model, two different speeds. What we know and what we don't.

**Model:** Liquid LFM2.5-2.6B, running locally on an 8 GB Apple M2 laptop through LM Studio. No cloud.

## The short version
We ran the same model on the same laptop twice and got **very different speeds**. We have a likely explanation, but we **haven't tested it yet**. What we can say with confidence is smaller than what we first wrote down.

## The two tests
| | Test A (my first benchmark) | Test B (Droid-built app) |
|---|---|---|
| Setup | Model loaded with a **very large 128K** memory window | Model loaded with a **small 4K** memory window |
| Input sizes | ~600 up to ~95,000 tokens | ~100 up to ~2,700 tokens |
| Speed once answering | **~10 tokens/sec** at ~2K tokens and above | **~33 tokens/sec** at ~2.7K tokens |
| Wait for first word | 8 sec at 2K, **7.7 min at 95K** | 0.6 to 7.8 sec |
| Memory (engine process) | ~2.4 to 2.8 GB | ~1.8 to 1.9 GB |
| Checked the answers? | **No** (token budget too small, no visible answer) | **Yes**, 3 of 3 correct |
| Runs per size | 1 | 1 |

(A token is roughly three-quarters of a word.)

## The puzzle
At nearly the same input size (about 2K to 2.7K tokens), Test A ran at 10 tokens/sec and Test B at 33. That's **3x apart on one machine**.

## Our best guess (not yet proven)
LM Studio's own estimate says the 128K setting needs about **6.6 GB** of memory, against about **2 GB** at 4K. On an 8 GB laptop that's very tight. The likely cause is that the large setting squeezed memory and slowed the model, not that the model is slow.

## What this means for Liquid's story
**Still holds, because it held in both tests:**
- A 2.6B model runs on an 8 GB laptop with roughly 1.8 GB for the model itself.
- It's interactive at short inputs, about 33 tokens/sec.
- It picks the right tool and fills in the arguments from plain text.
- It "thinks" before answering, and that thinking uses up the token budget.

**Now uncertain, so don't claim these:**
- *"Speed stays flat as context grows, which proves the architecture."* Test A's speed fell from 30 to 10 early, ran one time per size, and had no comparison model.
- *"Memory stays flat at 100K context."* The number we tracked may leave out memory the GPU holds. Treat it as unproven.
- *"It handles 100K tokens."* It did, but it took almost 8 minutes before the first word, and we never checked whether the answer was right.
- The gap to Liquid's advertised ~220 tokens/sec is still about 7x. We don't yet know whether the cause is the runtime, the laptop or the quantization.

**The honest customer message:** this fits **short, per-event tasks on a laptop** (Liquid's own pitch). Long context on small hardware is a **sizing decision**, and it has to be tested on the customer's actual hardware.

## What would settle it (about 10 minutes)
Same ~2K-token prompt, model loaded at 4K and then at 128K, 3 runs each, watching the Mac's memory-pressure graph.
- If 128K is slower **and** memory pressure turns red, the guess is right: the earlier "slow" numbers came from the setup.
- If both settings run at the same speed, the guess is wrong and we need to look at the runtime or the hardware.

## One line for a skeptical CTO
"Two runs disagreed by 3x. I traced it to a configuration difference and a memory estimate, I'm marking the explanation as a hypothesis, and here's the 10-minute test that proves or kills it."
