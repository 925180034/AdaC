type ScoreBarProps = {
  value: number
  label?: string
  tone?: 'cyan' | 'green' | 'violet' | 'amber' | 'red'
}

function clampScore(value: number): number {
  if (Number.isNaN(value)) return 0
  return Math.min(1, Math.max(0, value))
}

export function ScoreBar({ value, label = 'Score', tone = 'cyan' }: ScoreBarProps) {
  const score = clampScore(value)
  const percentage = Math.round(score * 100)

  const formattedScore = score.toFixed(2)

  return (
    <div
      className={`score-bar score-bar--${tone}`}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={score}
      aria-valuetext={`${formattedScore} out of 1 (${percentage}%)`}
    >
      <div className="score-bar__track">
        <span className="score-bar__fill" style={{ width: `${percentage}%` }} />
      </div>
      <span className="score-bar__value" aria-hidden="true">
        {formattedScore}
      </span>
    </div>
  )
}
