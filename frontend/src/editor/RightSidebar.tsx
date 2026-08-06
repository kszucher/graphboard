import { Box } from '@radix-ui/themes';
import { FullCodeEditor } from './FullCodeEditor';

interface RightSidebarProps {
  graphId: string;
  version: number | null;
}

export const RightSidebar = ({ graphId, version }: RightSidebarProps) => {
  return (
    <Box
      style={{
        width: '500px',
        minWidth: '500px',
        height: '100%',
        backgroundColor: '#1e1e1e',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
    >
      <FullCodeEditor graphId={graphId} version={version}/>
    </Box>
  );
};
