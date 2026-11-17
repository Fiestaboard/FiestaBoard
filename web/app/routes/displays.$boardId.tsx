import { DisplayDetail } from "@/components/displays/display-detail";
import { useParams } from "@/hooks/use-router";

export default function DisplayPage() {
  const { boardId = "" } = useParams<{ boardId: string }>();
  return <DisplayDetail key={boardId} boardId={boardId} />;
}
