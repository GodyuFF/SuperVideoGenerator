/**
 * 输入 `/` 时的 Skill 选择下拉。
 */

import type { SkillOption } from "../utils/skillCommand";

interface SkillPickerProps {
  skills: SkillOption[];
  activeIndex: number;
  onSelect: (skill: SkillOption) => void;
  onHover: (index: number) => void;
}

export function SkillPicker({
  skills,
  activeIndex,
  onSelect,
  onHover,
}: SkillPickerProps) {
  if (skills.length === 0) {
    return (
      <div className="skill-picker" role="listbox" aria-label="Skill 列表">
        <div className="skill-picker-empty">没有匹配的 Skill</div>
      </div>
    );
  }

  return (
    <div className="skill-picker" role="listbox" aria-label="Skill 列表">
      {skills.map((skill, index) => (
        <button
          key={skill.id}
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          className={
            index === activeIndex ? "skill-picker-item active" : "skill-picker-item"
          }
          onMouseEnter={() => onHover(index)}
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(skill);
          }}
        >
          <span className="skill-picker-id">/{skill.id}</span>
          <span className="skill-picker-title">{skill.title}</span>
          {skill.description ? (
            <span className="skill-picker-desc">{skill.description}</span>
          ) : null}
        </button>
      ))}
    </div>
  );
}
