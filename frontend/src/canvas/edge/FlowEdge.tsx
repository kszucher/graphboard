import { BaseEdge, type EdgeProps } from '@xyflow/react';
import { memo } from 'react';
import type { AppFlowEdge } from '../types.ts';
import { getRoundedOrthogonalPath } from './edgeUtils.ts';

function FlowEdge({
  selected,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style = {},
  markerEnd,
  data,
}: EdgeProps<AppFlowEdge>) {
  const sections = data?.sections;
  let path: string;

  if (sections && sections.length > 0) {
    const allPoints: { x: number; y: number }[] = [];
    path = sections
      .map((section) => {
        const start = section.startPoint;
        const end = section.endPoint;
        const bends = section.bendPoints ?? [];

        const points = [
          { x: start.x, y: start.y },
          ...bends.map((p) => ({ x: p.x, y: p.y })),
          { x: end.x, y: end.y },
        ];

        allPoints.push(...points);
        return getRoundedOrthogonalPath(points, 30);
      })
      .join(' ');
  } else {
    path = `M ${sourceX} ${sourceY} L ${targetX} ${targetY}`;
  }

  const isBack = targetX <= sourceX;
  const edgeStyle = {
    ...style,
    stroke: selected ? 'var(--accent-8)' : (isBack ? '#ff9800' : '#888888'),
    strokeWidth: selected ? 3 : 2,
    opacity: 1,
    transition: 'stroke 0.15s ease-in-out, stroke-width 0.15s ease-in-out',
  };

  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={edgeStyle}/>
    </>
  );
}

export default memo(FlowEdge, (prevProps, nextProps) => {
  return (
    prevProps.id === nextProps.id &&
    prevProps.selected === nextProps.selected &&
    prevProps.sourceX === nextProps.sourceX &&
    prevProps.sourceY === nextProps.sourceY &&
    prevProps.targetX === nextProps.targetX &&
    prevProps.targetY === nextProps.targetY &&
    JSON.stringify(prevProps.markerEnd) === JSON.stringify(nextProps.markerEnd) &&
    JSON.stringify(prevProps.data) === JSON.stringify(nextProps.data)
  );
});
