// What the game page says about the pace of the viewer on a game: their time against the rest of the group (those who
// completed it) and against the average time to complete (HowLongToBeat's). Pure, so it can be tested.
import { formatDuration } from './format.js';

/** "un 25 % más rápido que", "un 10 % más lento que" or "igual que", for a share of the reference time (100 = the same). */
function against(share) {
  if (share === 100) return 'igual que';
  return share < 100 ? `un ${100 - share} % más rápido que` : `un ${share - 100} % más lento que`;
}

/** The lines that tell the pace (`pace` is the API's, see crud/game_overview.pace): [] when there is nothing to say. */
export function paceLines(pace) {
  if (!pace) return [];
  const lines = [pace.completed ? `Lo completaste con ${formatDuration(pace.seconds)} de juego.` : `Llevas ${formatDuration(pace.seconds)} de juego.`];
  if (pace.group_share != null) {
    const who = pace.group_count === 1 ? '1 jugador lo ha completado' : `${pace.group_count} jugadores lo han completado`;
    lines.push(pace.completed
      ? `Eres ${against(pace.group_share)} el resto del grupo: ${formatDuration(pace.group_mean)} de media (${who}).`
      : `Es el ${pace.group_share} % de lo que ha tardado el resto del grupo: ${formatDuration(pace.group_mean)} de media (${who}).`);
  }
  if (pace.avg_share != null) {
    lines.push(pace.completed
      ? `Eres ${against(pace.avg_share)} HowLongToBeat (${formatDuration(pace.avg_time)}).`
      : `Es el ${pace.avg_share} % del tiempo medio de HowLongToBeat (${formatDuration(pace.avg_time)}).`);
  }
  return lines;
}
