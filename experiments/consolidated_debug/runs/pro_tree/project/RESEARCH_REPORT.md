# Research Report

Model-proposed claims are not independently verified unless an explicit verification reference is recorded.

<a id="root"></a>
## 1 CONSOLIDATED_GENUINE_PRO_TREE. Investigate the sharp cyclic mean-zero discrete Poincare inequality. For every integer N >= 3 and real cyclic sequence x_0,...,x_{N-1} with sum_j x_j=0 and x_N=x_0, determine the optimal C_N in sum_j x_j^2 <= C_N sum_j (x_{j+1}-x_j)^2, characterize its real equality space, and prove a quantitative near-extremizer stability theorem. Propose exactly two useful complementary tasks with positive weights summing to one: a DFT/eigenvalue/equality investigation and an elementary finite-sum or trigonometric-correlation verification with boundary and sharpness audits. Capacity four is an upper bound; create only these two mathematically useful leaves. Their research conversations use actual GPT-6 Pro; the coordinator uses actual GPT-6 Extra High. Plan three successive research rounds per child: first establish the sharp inequality and full two-dimensional real equality space; second derive deficit-to-distance stability with precise normalization; third audit optimal constants, near-extremizers and degeneracies. Treat N=3 and N=4 explicitly; do not invoke a nonexistent complementary spectral gap when the equality space is the entire mean-zero space. The elementary branch must distinguish independent finite-sum arguments from restated spectral arguments. Authorize only one initial round per child, then assess each exact report and save its next concrete task. Return concise complete reports, aiming around 700 words while preserving essential proof. No external data or software execution. Do not claim independent verification. [ACTIVE]

Node: `root`

Claim status: **MODEL_PROPOSED**

CONSOLIDATED RESEARCH RESULT — Both original GPT-6 Pro research branches have completed their three planned rounds. The DFT branch has submitted a final spectral audit, complementing the elementary branch's reflection-averaged finite-sum audit. Their principal mathematical conclusions agree.

For every integer N>=3 and every real cyclic mean-zero vector x, the sharp inequality is M(x)<=C_N E(x), where C_N=1/[4sin^2(pi/N)]. Equality holds exactly on the two-dimensional real space V_N=span_R{(cos(2pi j/N))_j,(sin(2pi j/N))_j}.

For N>=4, writing lambda_1=4sin^2(pi/N), the optimal quantitative refinement is E(x)-lambda_1 M(x)>=gamma_N dist(x,V_N)^2, where gamma_N=4sin^2(2pi/N)-4sin^2(pi/N)=4sin(3pi/N)sin(pi/N)>0. Equality holds exactly on V_N orthogonal-direct-sum W_N, with W_N the real second-harmonic space. For N=4, W_N has dimension one; for N>=5, it has dimension two.

For nonzero x and epsilon>=0, the sharp relative-distance estimate under E(x)/M(x)<=lambda_1+epsilon is dist(x,V_N)/||x||_2<=min{1,sqrt(epsilon/gamma_N)}. Orthogonal first-plus-second harmonic mixtures establish optimality, including the square-root coefficient for arbitrarily small positive epsilon.

Exceptional cases are resolved. For N=3, E=3M on the entire mean-zero space and no complementary stability coefficient exists. For N=4, gamma_4=2 and stability is an identity. For N=5, gamma_5=sqrt(5) and stability is again an identity. For N>=6, higher harmonics yield strict stability inequality.

The spectral branch derives the results through explicit DFT diagonalization, while the elementary branch derives global positivity through reflection averaging and finite-sum square factorizations. Both report complete equality and sharpness audits. No substantive unresolved mathematical issue was identified in their final reports. The findings are model-generated and coordinator-assessed; no independent external verification has been performed. All six planned leaf research rounds are complete, and no additional research leaves are needed.

Evidence: n-dab935ae44d1-r000003; n-3790f8503746-r000003

<a id="n-3790f8503746"></a>
### 1.1 Elementary finite-sum and trigonometric-correlation verification: seek a genuinely independent proof of the sharp cyclic inequality, validate equality and constants by exact finite calculations, and audit exceptional cases without disguising spectral arguments as elementary independence. [PAUSED]

Node: `n-3790f8503746`

Claim status: **MODEL_PROPOSED**

The algebraic audit found no error in either theorem. The proof below supplies explicit parity-dependent boundary checks, verifies every coefficient in the dual factorization, resolves the singleton and two-vertex equality cases, and establishes sharpness and normalization. This is a same-branch mathematical audit, not a claim of independent external verification.

DEFINITIONS AND PROJECTION. Assume N≥3, x real and N-periodic, and ∑_j x_j=0. All cyclic sums range over 0,...,N−1. Set θ=2π/N, λ₁=2−2cosθ=4sin²(π/N), λ₂=2−2cos(2θ)=4sin²θ, M(u)=∑u_j², E(u)=∑(u_{j+1}−u_j)², and D(u)=E(u)−λ₁M(u). Let V_N and W_N be the real spans of the first and second cosine and sine harmonics, respectively. For N≥4, γ=λ₂−λ₁=2cosθ−2cos(2θ)=λ₁(1+2cosθ)>0.

The geometric-sum identity (1−q)∑_{j=0}^{N−1}q^j=1−q^N proves that ∑_j exp(ikθj) is zero unless N divides k, when it is N. Taking real and imaginary parts and using product-to-sum identities proves that the first cosine and sine have zero means, squared norms N/2, and inner product zero. Consequently v=P_Nx is given by v_j=a cos(θj)+b sin(θj), where a=(2/N)∑_l x_l cos(θl) and b=(2/N)∑_l x_l sin(θl). The vector z=x−v has zero mean and is perpendicular to V_N. For every u∈V_N, M(x−u)=M(z)+M(v−u), proving dist(x,V_N)²=M(z).

Cyclic summation by parts gives ∑_j Δv_j Δz_j=∑_j(2v_j−v_{j−1}−v_{j+1})z_j. Trigonometric addition makes the latter expression λ₁∑v_jz_j and also gives E(v)=λ₁M(v). Expanding D(v+z) therefore proves D(x)=D(z).

A. CYCLIC GEOMETRY. For any mean-zero u, define y_j=u_j−u_{r−j}, s_j=sin(θ(j−r/2)), and t_j=y_j/s_j when s_j≠0, with t_j=0 otherwise. Extend all sequences to integer indices periodically. Sine-zero positions on this lift are (r+kN)/2. A zero vertex satisfies 2j≡r modulo N and is fixed by reflection, so y_j=0 there. Positive-sine vertices are precisely the integers in (r/2,(r+N)/2); they form one consecutive arc. Reflection maps this arc bijectively onto the negative arc.

The triples (number of zero vertices, number of sign-changing edges, positive-arc length m) are (1,1,(N−1)/2) for odd N; (2,0,N/2−1) for even N with even r; and (0,2,N/2) for even N with odd r. Thus N=3 gives (1,1,1); N=4 gives (2,0,1) or (0,2,2); N=5 gives (1,1,2); and N=6 gives (2,0,2) or (0,2,3), with the alternatives ordered by even and odd r.

Every negative-weight edge crosses a half-integer zero j+1/2, since consecutive sine zeros are N/2>1 indices apart. Hence 2j+1≡r modulo N: reflection exchanges its endpoints. Both y and s change sign, so t_{j+1}=t_j. This applies at either sign-changing boundary. The closing edge is represented by (N−1,N), so the same integer-lift argument covers it. Reflection also bijects the m−1 positive-arc internal edges with the negative-arc internal edges, reversing orientation but preserving weights and squared differences. There are no missing or duplicated positive-weight contributions.

FIRST FACTORIZATION. Expansion and s_{j−1}+s_{j+1}=2cosθ s_j give
D(y)=∑_j s_js_{j+1}(t_{j+1}−t_j)².
Indeed, the coefficient of t_j² is s_j(s_{j−1}+s_{j+1})=2cosθ s_j², and each mixed term is −2y_jy_{j+1}. Negative-weight terms vanish as just proved; zero weights vanish without division.

Relabel the positive-arc angles as h₁,...,h_m∈(0,π), with spacing θ, and set w_i=sin²h_i, a_i=sin h_i sin h_{i+1}, S=∑_{i=1}^m w_it_i², and T=∑_{i=1}^{m−1}a_i(t_{i+1}−t_i)². Thus M(y)=2S and D(y)=2T. Expanding y_j² and (Δy_j)², with Δy_j=Δu_j+Δu_{r−j−1}, gives ∑_r M(y^(r))=2NM(u), ∑_r D(y^(r))=2ND(u), and ∑_r y_j^(r)=Nu_j. Therefore D(u)≥0. Equality forces t constant on each positive arc, including a singleton; reflection extends that constant to the negative arc. Hence y^(r) is a multiple of s^(r), and reconstruction gives u∈V_N. The first-harmonic recurrence proves the converse.

B. FLUX AND DUAL FACTORIZATION. Now use u=z. Since s^(r)∈V_N, ∑_j y_js_j=2∑_j z_js_j=0, giving ∑_i w_it_i=0. When m=1 this forces y=0. Assume m≥2. Set φ_i=cos h_i and p_i=a_i(φ_i−φ_{i+1}) for 1≤i<m. All w_i, a_i, and these internal p_i are strictly positive; cosine is strictly decreasing on (0,π). Set p₀=p_m=0.

These endpoint fluxes are genuine zeros. The left neighboring angle pair is either (0,θ) or (−θ/2,θ/2); the right pair is either (π−θ,π) or (π−θ/2,π+θ/2). In the first case the neighboring sine vanishes; in the second the cosines coincide, even though the sine product is negative. Thus the omitted flux is zero in every parity case.

Using these extended neighboring angles, trigonometric addition gives, at every i including both endpoints,
p_i−p_{i−1}=sin h_i[(sin(h_i−θ)+sin(h_i+θ))cos h_i−sin(h_i−θ)cos(h_i−θ)−sin(h_i+θ)cos(h_i+θ)]=γw_iφ_i.
Here the two sums have factors 2cosθ and 2cos(2θ), respectively.

Define F_i=∑_{k=1}^i w_kt_k, so F₀=F_m=0, and J=∑_{i=1}^{m−1}F_i²/a_i. Then S=∑_{i=1}^m(F_i−F_{i−1})²/w_i. Subtracting consecutive flux relations after division by their weights proves
1/w_i+1/w_{i+1}−γ/a_i=p_{i−1}/(w_ip_i)+p_{i+1}/(w_{i+1}p_i),  1≤i<m.
Thus the diagonal coefficients of S−γJ agree exactly with those of
K:=∑_{i=1}^{m−2}[p_ip_{i+1}/w_{i+1}](F_i/p_i−F_{i+1}/p_{i+1})².
Both mixed coefficients are −2/w_{i+1}. This proves K=S−γJ≥0, including endpoint coefficients. For m=2, the diagonal relation says γ=a₁(1/w₁+1/w₂), so K=0, exactly as its empty sum requires. No zero endpoint p is ever divided by.

Finite summation by parts gives ∑_{i=1}^{m−1}F_i(t_{i+1}−t_i)=−∑_{i=1}^m(F_i−F_{i−1})t_i=−S. Expanding squares consequently proves
T−γS=∑_{i=1}^{m−1}a_i(t_{i+1}−t_i+γF_i/a_i)²+γK≥0.
The averaging factors are therefore
D(z)−γM(z)=(1/N)∑_r(T_r−γS_r)≥0.
Together with the projection identities, this establishes the claimed stability inequality.

C. COMPLETE EQUALITY AND SHARPNESS. In the weighted inequality, m=1 permits only y=0. For m=2 write F₁=κp₁; for m≥3, equality implies K=0, whose positive coefficients force all F_i/p_i to equal some κ. In either case m≥2, t_i=(F_i−F_{i−1})/w_i=κγcos h_i. Conversely, this form has weighted mean zero by telescoping the flux relation, and every remaining square vanishes because t_{i+1}−t_i=−κγp_i/a_i. These conditions are therefore necessary and sufficient.

It follows on the positive arc that y_j=(κγ/2)sin(2θ(j−r/2)); reflection extends the formula to the negative arc, and both sides vanish at zero vertices. Singleton cases use coefficient zero. In particular, for N=4 and even r the entire second-harmonic reflection profile vanishes, consistently with m=1. Global equality forces every local equality, and z_j=N⁻¹∑_r y_j^(r) consequently belongs to W_N.

Finite geometric sums at frequencies 1,2,3 prove W_N is perpendicular to constants and V_N for N≥4. For N≥5, the frequency-4 sum also proves that its cosine and sine have squared norms N/2 and inner product zero; hence dim W_N=2. For N=4 its sine vanishes and its cosine is (−1)^j, of squared norm 4, so dim W_4=1. The direct recurrence 2w_j−w_{j−1}−w_{j+1}=λ₂w_j gives E(w)=λ₂M(w), hence D(w)=γM(w). This proves the converse equality statement and optimality of γ using a nonzero second cosine. A nonzero first cosine similarly proves optimality of λ₁. Stability equality is exactly x∈V_N+W_N; original Poincare equality is exactly x∈V_N.

D. EXCEPTIONAL CASES AND NORMALIZATION. For N=3, zero mean gives ∑_{i<j}x_ix_j=−M/2, so E=2M−2∑_{i<j}x_ix_j=3M. The two-dimensional V_3 equals the mean-zero space. Thus D=dist²=0, every finite stability coefficient works vacuously, and no finite optimal complementary coefficient exists.

For N=4, put σ=x₀+x₂. Direct calculation gives x−P₄x=(σ/2)(1,−1,1,−1), so dist²=σ², while D=−2(x₀+x₂)(x₁+x₃)=2σ². Thus D=2dist² identically. For N=5, writing c=cos(2π/5)>0, the finite cosine sum gives 1+2c+2(2c²−1)=0, hence c=(√5−1)/4 and γ₅=√5. The orthogonal spaces V_5 and W_5 have total dimension four, exhausting the mean-zero space, so D=√5dist² identically. For N=6, the higher harmonic u_j=(−1)^j is perpendicular to V_6 and W_6 by the same finite sums. It has M=6, E=24, λ₁=1, and γ=2, giving D=18>12=γdist².

The sharp Poincare constant is C_N=1/λ₁, and division by λ₁ yields C_NE−M≥(γ/λ₁)dist²=(1+2cosθ)dist² for N≥4. Under x→αx, E, M, D, and dist² all scale by α². There are no normalized-sum factors.

E. NEAR EXTREMIZERS. For N≥4 and x≠0, stability and orthogonal projection give γdist²/M≤D/M and dist²/M≤1. Therefore E/M≤λ₁+ε, ε≥0, implies dist/||x||₂≤min{1,sqrt(ε/γ)}. Equivalently, C_NE/M≤1+δ implies dist/||x||₂≤min{1,sqrt(δ/(1+2cosθ))}, with δ≥0 and δ=ε/λ₁ for corresponding thresholds.

Choose unit vectors v∈V_N and w∈W_N. They are perpendicular, and x=v+tw satisfies E/M=λ₁+γt²/(1+t²) and dist/||x||₂=|t|/sqrt(1+t²). For 0≤ε<γ take t=sqrt(ε/(γ−ε)); for ε=γ take x=w. These attain the bound exactly. For ε>γ, the same pure second harmonic attains the truncated bound 1. Thus the coefficient is optimal even for arbitrarily small ε. At fixed N, ε→0 forces normalized approach to V_N; an arbitrary positive ε need not be small. The zero vector satisfies the homogeneous inequalities but has no Rayleigh quotient.

METHODOLOGICAL CONCLUSION. The trigonometric recurrences are individual eigenfunction calculations in substance. The global positivity and equality proofs, however, come from explicitly verified finite-sum factorizations and reflection reconstruction, not complete Fourier diagonalization, spectral ordering, or an assumed coercivity statement.

Evidence: n-3790f8503746-r000003

<a id="n-dab935ae44d1"></a>
### 1.2 DFT and eigenvalue investigation: rigorously establish the optimal cyclic mean-zero Poincare constant, prove the complete two-dimensional real equality space, and prepare a spectral foundation for sharp stability and degeneracy audits. [PAUSED]

Node: `n-dab935ae44d1`

Claim status: **MODEL_PROPOSED**

Completed the spectral audit and consolidated the sharp Poincare and stability theorems, including all equality cases, normalization factors, small-N exceptions, and optimal near-extremizer bounds. No error was detected in the supplied spectral conclusions. The deductions below are not independent external verification; the elementary branch's unsupplied factorizations remain outside this verification.

THEOREM. Let U_N = {x ∈ R^N : ∑_j x_j = 0}, with cyclic indices and ordinary Euclidean norm. Put r = dist(x,V_N). Then M(x) ≤ C_NE(x), with the optimal constant and equality space stated above. For N ≥ 4, the sharp refinement is E(x) ≥ λ_1M(x)+γ_Nr², with equality exactly on V_N ⊕ W_N. The optimal relative-distance modulus is the capped square-root bound stated above. The following calculations prove these assertions and their exceptional cases.

FOURIER NORMALIZATION. All Fourier sums use distinct residues 0,…,N−1. Finite geometric summation gives ∑_jω^((k−ℓ)j) = N if k ≡ ℓ modulo N, and zero otherwise. Substituting x̂_k = (1/N)∑_j x_jω^(−kj) and using this identity proves inversion x_j = ∑_k x̂_kω^(kj). Expanding squared moduli and applying the same identity gives Parseval, M = N∑_k|x̂_k|². Cyclic reindexing yields (Dx)̂_k = (ω^k−1)x̂_k for (Dx)_j = x_{j+1}−x_j. Since |ω^k−1|² = 2−2cos(2πk/N) = λ_k, we obtain E = N∑_kλ_k|x̂_k|². Direct cyclic summation also gives
E = 2M−2∑_j x_jx_{j+1} = ∑_j x_j(2x_j−x_{j−1}−x_{j+1}) = ⟨x,Lx⟩.
Thus L has Fourier eigenvalues λ_k. Mean zero is precisely x̂_0 = 0.

FIRST EIGENSPACE AND PROJECTION. For nonzero k, write d(k) = min(k,N−k). Strict increase of sin² on [0,π/2] shows that λ_k is minimized exactly when d(k) = 1, namely at the distinct residues 1,N−1. Real conjugate symmetry x̂_(N−k) = conj(x̂_k) converts this support into x_j = A cos(2πj/N)+B sin(2πj/N). Because N does not divide 2, ∑_jω^(2j) = 0, yielding ⟨c,s⟩ = 0 and ‖c‖² = ‖s‖² = N/2. Hence V_N has real dimension two for every N ≥ 3. The nonzero vector c satisfies E(c) = λ_1M(c), proving both claimed optimal interpretations of the constants.
The projection is P_Nx = (2/N)(⟨x,c⟩c+⟨x,s⟩s). For every v ∈ V_N, orthogonality gives ‖x−v‖² = ‖x−P_Nx‖²+‖P_Nx−v‖², proving the distance formula.

STABILITY AND ITS EQUALITY CASES. Let R_N = {k : 0 ≤ k < N, k ∉ {0,1,N−1}}. Parseval gives
r² = N∑_{k∈R_N}|x̂_k|²,    D_N = N∑_{k∈R_N}(λ_k−λ_1)|x̂_k|².
For N ≥ 4, complementary frequencies have 2 ≤ d(k) ≤ floor(N/2). The distinct spectral levels satisfy λ_1 < λ_2 < ⋯ < λ_floor(N/2), with the chain ending at λ_2 when floor(N/2) = 2. Therefore λ_k ≥ λ_2 on R_N, with equality exactly at residues {2,N−2}. Trigonometric identities give
γ_N = 4sin(3π/N)sin(π/N) = λ_1[1+2cos(2π/N)] > 0.
Both sine factors are positive, including at N = 4. Consequently,
D_N−γ_Nr² = N∑_{k∈R_N}(λ_k−λ_2)|x̂_k|² ≥ 0.
The factor N occurs in both deficit and distance, so the Euclidean-distance coefficient is exactly γ_N. It is the smallest eigenvalue of L−λ_1I restricted to U_N ∩ V_N^⊥.
Equality holds if and only if Fourier support is contained in {1,N−1,2,N−2}. For N ≥ 5, conjugate symmetry identifies W_N with the real span of cos(4πj/N) and sin(4πj/N). Their orthogonality and squared norms N/2 follow from ∑_jω^(4j) = 0; thus W_N has dimension two. For N = 4, the labels 2 and N−2 coincide: the sine vanishes and W_4 = span_R{((−1)^j)_j}, of dimension one. Disjoint Fourier supports give V_N ⟂ W_N. Every v+w in this direct sum attains stability equality, whereas original Poincare equality requires w = 0. Any nonzero w ∈ W_N has D_N(w) = γ_N‖w‖² and r² = ‖w‖², excluding every larger stability coefficient.

SMALL-N AND NYQUIST AUDIT. For N = 3, the full spectrum is (0,3,3). Hence U_3 = V_3 and E = 3M, so D_3 = r = 0. Every finite coefficient in D_3 ≥ Kr² works vacuously; there is no complementary eigenvalue or largest finite coefficient.
For N = 4, the spectrum is (0,2,4,2), so γ_4 = 2. Mean zero gives x−P_4x = ((x_0+x_2)/2)(1,−1,1,−1). Therefore
D_4(x) = 2r² = 2(x_0+x_2)².
For N = 5, frequencies {1,4} and {2,3} exhaust the mean-zero space. To evaluate their eigenvalues, fifth-root summation gives u²+u−1 = 0 for u = 2cos(2π/5)>0. Thus λ_1 = (5−√5)/2, λ_2 = (5+√5)/2, and γ_5 = √5. Consequently D_5 = √5r² identically.
For N = 6, the full spectrum is (0,1,3,4,3,1), and D_6−2r² = 6|x̂_3|². For every even N ≥ 6, the Nyquist residue N/2 is self-conjugate, has one real dimension and eigenvalue 4 > λ_2, and is counted once. For every N ≥ 6, stability is strict exactly when some coefficient with d(k) ≥ 3 is nonzero.

NEAR-EXTREMIZERS AND NORMALIZATION. For x ≠ 0, let ρ = r/√M. Orthogonal projection gives ρ ≤ 1. If E/M ≤ λ_1+ε, then γ_Nr² ≤ D_N ≤ εM, proving ρ ≤ min{1,√(ε/γ_N)}. Put q_N = γ_N/λ_1 = 1+2cos(2π/N). The equivalent undivided refinement is C_NE−M ≥ q_Nr². Therefore (C_NE−M)/M ≤ η implies ρ ≤ min{1,√(η/q_N)}. The two slack parameters correspond through ε = λ_1η.

SHARPNESS AND COMPLETE PARAMETER CASES. Choose unit vectors v = √(2/N)c and w = √(2/N)(cos(4πj/N))_j for N ≥ 5; for N = 4 choose w = ((−1)^j/2)_j. They are orthogonal. For x_t = v+tw,
M = 1+t²,    E = λ_1+λ_2t²,    D_N = γ_Nt²,    r² = t².
Its Rayleigh excess is ε_t = γ_Nt²/(1+t²), and ρ = √(ε_t/γ_N). For 0 ≤ ε < γ_N, taking t = √(ε/(γ_N−ε)) attains the bound exactly. Hence no o(√ε) modulus or leading coefficient smaller than γ_N^(−1/2) is possible.
More precisely, at ε = 0, equality consists of all nonzero vectors in V_N. For 0 < ε < γ_N, equality holds exactly for x = v_0+w_0 ∈ V_N ⊕ W_N with ‖w_0‖²/M = ε/γ_N; both components are nonzero. At ε = γ_N, equality requires exactly a nonzero pure second harmonic x ∈ W_N. Fixed nonzero v in x_t only approaches that endpoint as |t| tends to infinity. For ε > γ_N, equality in the capped bound holds exactly when P_Nx = 0 within the assumed Rayleigh class; x = w always supplies an example. Equality in the uncapped square-root bound is then impossible. Thus the capped bound is attained for every ε ≥ 0, while the uncapped equality range is [0,γ_N], or [0,q_N] in normalized slack η.
All undivided inequalities include x = 0; no ratio is assigned to it. Under x ↦ ax, all quadratic quantities multiply by a², P_N(ax) = aP_Nx, and the ratio statements are invariant when a ≠ 0.

ELEMENTARY-BRANCH COMPARISON. The reported coefficients, equality spaces, and near-extremizer statements agree. Useful technical cross-checks follow directly from the audited spectrum. For any harmonic Lu = λ_du, its flux F_j = u_{j+1}−u_j obeys F_j−F_{j−1} = −λ_du_j, and hence F_b−F_a = −λ_d∑_{j=a+1}^b u_j. These identities follow by expansion and telescoping. For u_j = sin(2πdj/N), positivity requires phase modulo 2π in (0,π), and zeros occur precisely when N divides 2dj; divisions by sine must respect these nodes. In particular, the second-harmonic sine vanishes identically at N = 4. Any elementary remainder factorization must reproduce the kernel V_N for D_N and V_N ⊕ W_N for D_N−γ_Nr², including its identical vanishing throughout U_4 and U_5 and its rank-one form at N = 6. These are explicit consistency tests, not verification of the elementary branch's unsupplied technical factorizations. No spectral correction or unresolved spectral issue remains in this audit.

Evidence: n-dab935ae44d1-r000003
