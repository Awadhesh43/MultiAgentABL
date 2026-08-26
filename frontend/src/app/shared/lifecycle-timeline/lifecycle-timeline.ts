import { Component, computed, input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { LIFECYCLE_STAGES, StageEvent, WORKOUT_STAGE } from '../../core/models';

type StepState = 'completed' | 'in_progress' | 'not_started';

interface Step {
  id: string;
  label: string;
  state: StepState;
  notes: string;
}

@Component({
  selector: 'app-lifecycle-timeline',
  imports: [MatIconModule, MatTooltipModule],
  templateUrl: './lifecycle-timeline.html',
  styleUrl: './lifecycle-timeline.scss',
})
export class LifecycleTimeline {
  stageEvents = input.required<StageEvent[]>();

  protected steps = computed<Step[]>(() => {
    const byStage = new Map(this.stageEvents().map((e) => [e.stage, e]));
    return LIFECYCLE_STAGES.map((s) => {
      const event = byStage.get(s.id);
      return {
        id: s.id,
        label: s.label,
        state: (event?.status === 'completed' ? 'completed' : event?.status === 'in_progress' ? 'in_progress' : 'not_started') as StepState,
        notes: event?.notes ?? '',
      };
    });
  });

  protected workoutStep = computed<Step | null>(() => {
    const event = this.stageEvents().find((e) => e.stage === WORKOUT_STAGE.id);
    if (!event) return null;
    return { id: WORKOUT_STAGE.id, label: WORKOUT_STAGE.label, state: event.status === 'completed' ? 'completed' : 'in_progress', notes: event.notes };
  });
}
